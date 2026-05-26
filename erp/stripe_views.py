import stripe
import os
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Tenant
from django.contrib import messages
from datetime import timedelta
from django.utils import timezone

# Cargamos las claves desde el .env
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

STRIPE_WEBHOOK_SECRET  = os.getenv('STRIPE_WEBHOOK_SECRET')
STRIPE_PRICE_BASIC     = os.getenv('STRIPE_PRICE_BASIC')   # price_xxx del plan básico
STRIPE_PRICE_PRO       = os.getenv('STRIPE_PRICE_PRO')     # price_xxx del plan pro

# Mapeo de Price ID → nombre del plan en tu BD
PLAN_MAP = {
    STRIPE_PRICE_BASIC: 'basic',
    STRIPE_PRICE_PRO:   'pro',
}


@require_POST
@login_required
def redeem_promo_code(request):
    codigo_ingresado = request.POST.get('promo_code', '').strip().upper()
    tenant = request.user.tenantuser.tenant

    # Nuestro código "Bomba" maestro
    CODIGO_SECRETO = "PYME7PRO"

    # Verificamos que el código sea correcto y que NO haya tomado la prueba antes
    if codigo_ingresado == CODIGO_SECRETO:
        if tenant.trial_ends_at:
            # Ya usó un demo antes, no se vale hacer trampa
            messages.error(request, "Ya has utilizado un código de prueba anteriormente.")
        else:
            # ¡Bomba activada! Le damos 7 días desde este exacto momento
            tenant.trial_ends_at = timezone.now() + timedelta(days=7)
            tenant.save()
            messages.success(request, "¡Código VIP activado! Disfruta 7 días de Pro gratis.")
    else:
        messages.error(request, "Código inválido.")

    # Lo regresamos a la pantalla de planes para que vea su estatus actualizado
    return redirect('pricing')

# ==========================================
# VISTA 1: Página de precios
# ==========================================
@login_required
def pricing_view(request):
    """
    Muestra los planes disponibles.
    Pasa la clave pública de Stripe al template (no la secreta).
    """
    context = {
        'current_plan': request.user.tenantuser.tenant.plan,
        'stripe_pk': os.getenv('STRIPE_PUBLISHABLE_KEY'),
        'price_basic': STRIPE_PRICE_BASIC,
        'price_pro': STRIPE_PRICE_PRO,
    }
    return render(request, 'pricing.html', context)


# ==========================================
# VISTA 2: Crear sesión de checkout
# ==========================================
@login_required
def create_checkout_session(request, price_id):
    """
    Crea una sesión de Stripe Checkout para el plan elegido.
    Redirige al usuario a la página de pago de Stripe.
    """
    tenant = request.user.tenantuser.tenant

    try:
        # Si el tenant ya tiene un customer en Stripe, lo reutilizamos
        # Si no, Stripe creará uno automáticamente y lo linkeamos después via webhook
        customer_kwargs = {}
        if tenant.stripe_customer_id:
            customer_kwargs['customer'] = tenant.stripe_customer_id

        session = stripe.checkout.Session.create(
            **customer_kwargs,
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            # Guardamos el tenant_id en los metadatos para identificarlo en el webhook
            metadata={'tenant_id': tenant.id},
            # URLs de retorno después del pago
            success_url=request.build_absolute_uri('/planes/exito/'),
            cancel_url=request.build_absolute_uri('/planes/'),
        )
        return redirect(session.url)

    except stripe.error.StripeError as e:
        return JsonResponse({'error': str(e)}, status=400)


# ==========================================
# VISTA 3: Página de éxito después del pago
# ==========================================
@login_required
def checkout_success(request):
    """
    Stripe redirige aquí después de un pago exitoso.
    Solo es una página de confirmación visual — la activación
    real del plan ocurre en el webhook (más confiable).
    """
    return render(request, 'checkout_success.html')


# ==========================================
# VISTA 4: Portal del cliente (autogestión)
# ==========================================
@login_required
def customer_portal(request):
    """
    Redirige al portal de Stripe donde el cliente puede:
    - Ver sus facturas
    - Cambiar su método de pago
    - Cancelar su suscripción
    Todo sin que tengas que construir esa UI.
    """
    tenant = request.user.tenantuser.tenant

    if not tenant.stripe_customer_id:
        return redirect('pricing')

    portal_session = stripe.billing_portal.Session.create(
        customer=tenant.stripe_customer_id,
        return_url=request.build_absolute_uri('/dashboard/'),
    )
    return redirect(portal_session.url)


# ==========================================
# VISTA 5: Webhook de Stripe (el cerebro)
# ==========================================
@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Stripe llama a este endpoint con cada evento importante.
    NUNCA confíes en el frontend para activar planes —
    siempre usa el webhook como fuente de verdad.

    Eventos que manejamos:
    - checkout.session.completed  → activar suscripción
    - customer.subscription.updated → cambio de plan
    - invoice.payment_failed      → degradar a básico
    - customer.subscription.deleted → cancelación
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    # Verificamos que el evento realmente viene de Stripe
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        # Firma inválida — rechazamos con 400
        return HttpResponse(status=400)

    event_type = event['type']
    data = event['data']['object']

    # --- EVENTO: Pago completado exitosamente ---
    if event_type == 'checkout.session.completed':
        tenant_id = data.get('metadata', {}).get('tenant_id')
        if not tenant_id:
            return HttpResponse(status=200)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
            # Guardamos los IDs de Stripe en nuestro Tenant
            tenant.stripe_customer_id     = data.get('customer')
            tenant.stripe_subscription_id = data.get('subscription')
            # Activamos el plan según el price_id de la sesión
            # (Stripe incluye el line_item en el objeto de la sesión)
            tenant.save()
        except Tenant.DoesNotExist:
            pass

    # --- EVENTO: Suscripción actualizada (upgrade/downgrade) ---
    elif event_type == 'customer.subscription.updated':
        _actualizar_plan_desde_subscription(data)

    # --- EVENTO: Pago de factura fallido ---
    elif event_type == 'invoice.payment_failed':
        customer_id = data.get('customer')
        _degradar_tenant(customer_id)

    # --- EVENTO: Suscripción cancelada ---
    elif event_type == 'customer.subscription.deleted':
        customer_id = data.get('customer')
        _degradar_tenant(customer_id)

    # Siempre respondemos 200 para que Stripe sepa que recibimos el evento
    return HttpResponse(status=200)


# ==========================================
# FUNCIONES AUXILIARES INTERNAS
# ==========================================

def _actualizar_plan_desde_subscription(subscription_data):
    """
    Lee los items de una suscripción de Stripe y actualiza
    el campo 'plan' del Tenant correspondiente.
    """
    customer_id = subscription_data.get('customer')
    try:
        tenant = Tenant.objects.get(stripe_customer_id=customer_id)
        items = subscription_data.get('items', {}).get('data', [])
        if items:
            price_id = items[0].get('price', {}).get('id')
            nuevo_plan = PLAN_MAP.get(price_id, 'basic')
            tenant.plan = nuevo_plan
            tenant.save()
    except Tenant.DoesNotExist:
        pass


def _degradar_tenant(customer_id):
    """
    Baja el plan a 'basic' cuando hay un fallo de pago o cancelación.
    """
    try:
        tenant = Tenant.objects.get(stripe_customer_id=customer_id)
        tenant.plan = 'basic'
        tenant.stripe_subscription_id = None
        tenant.save()
    except Tenant.DoesNotExist:
        pass