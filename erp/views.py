import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Product, Customer, Sale , FinancialMovement ,SaleItem
from django.http import JsonResponse
from .ai_agent import chat_with_agent
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib.auth.models import User
from django.contrib.auth import login
from .models import Tenant, TenantUser
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractDay
import calendar
from django.shortcuts import render, redirect, get_object_or_404
from .models import Supplier, PurchaseOrder, PurchaseItem, Product



@login_required
def purchases_view(request):
    """
    Muestra el panel de compras: lista de proveedores y órdenes de compra.
    También procesa la creación de nuevos proveedores vía POST.
    """
    mi_tenant = request.user.tenantuser.tenant
    
    if request.method == 'POST' and 'add_supplier' in request.POST:
        # Registrar un nuevo proveedor
        name = request.POST.get('name')
        contact = request.POST.get('contact')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        
        Supplier.objects.create(
            tenant=mi_tenant,
            name=name,
            contact_name=contact,
            phone=phone,
            email=email
        )
        return redirect('purchases')

    # Consultas para llenar las tablas
    suppliers = Supplier.objects.filter(tenant=mi_tenant).order_by('name')
    orders = PurchaseOrder.objects.filter(tenant=mi_tenant).order_by('-created_at')
    products = Product.objects.filter(tenant=mi_tenant).order_by('name')

    context = {
        'suppliers': suppliers,
        'orders': orders,
        'products': products,
    }
    return render(request, 'purchases.html', context)


@login_required
@transaction.atomic
def create_purchase_order_api(request):
    """
    Procesa el formulario de una nueva compra, suma el stock al inventario
    y genera el movimiento financiero de gasto automáticamente.
    """
    if request.method == 'POST':
        mi_tenant = request.user.tenantuser.tenant
        supplier_id = request.POST.get('supplier_id')
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 0))
        cost_price = float(request.POST.get('cost_price', 0.0))
        
        if quantity <= 0 or cost_price <= 0:
            return redirect('purchases')
            
        supplier = get_object_or_404(Supplier, id=supplier_id, tenant=mi_tenant)
        product = get_object_or_404(Product, id=product_id, tenant=mi_tenant)
        
        # 1. Calcular el costo total de este reabastecimiento
        total_cost = quantity * cost_price
        
        # 2. Crear la Orden de Compra marcada directamente como 'received' (Recibida)
        order = PurchaseOrder.objects.create(
            tenant=mi_tenant,
            supplier=supplier,
            total_cost=total_cost,
            status='received',
            received_at=timezone.now()
        )
        
        # 3. Registrar el artículo comprado en el detalle
        PurchaseItem.objects.create(
            purchase_order=order,
            product=product,
            quantity=quantity,
            cost_price=cost_price
        )
        
        # 4. LA MAGIA: Sumamos el stock al producto en la base de datos
        product.stock += quantity
        # Opcional: Actualizamos su precio de costo real si varió con el proveedor
        product.cost_price = cost_price 
        product.save()
        
        # 5. Registramos la salida de dinero en Finanzas como 'gasto'
        FinancialMovement.objects.create(
            tenant=mi_tenant,
            movement_category='gasto',
            amount=total_cost,
            is_cleared=True,
            due_date=timezone.now().date()
            # Si tu modelo tiene un campo 'description', puedes poner: description=f"Compra de mercancía a {supplier.name}"
        )
        
    return redirect('purchases')



@login_required
def sales_chart_api(request):
    """
    API que calcula las ventas agregadas para la gráfica
    dependiendo de los filtros de año, mes y semana.
    """
    mi_tenant = request.user.tenantuser.tenant
    
    # 1. Capturar los filtros de la URL (con valores por defecto)
    year = request.GET.get('year', 2026)
    month = request.GET.get('month', 'all')
    week = request.GET.get('week', 'all')
    
    # Base de filtrado por Tenant y Año
    sales_query = Sale.objects.filter(tenant=mi_tenant, created_at__year=year)
    
    labels = []
    data = []
    
    # CASO A: Ver todo el año (Desglose por meses)
    if month == 'all':
        labels = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        data = [0.0] * 12
        
        # Agrupamos por mes y sumamos
        monthly_totals = sales_query.annotate(
            m=ExtractMonth('created_at')
        ).values('m').annotate(total=Sum('total')).order_by('m')
        
        for item in monthly_totals:
            if item['m'] and 1 <= item['m'] <= 12:
                data[item['m'] - 1] = float(item['total'])
                
    # CASO B: Ver un mes específico
    else:
        month_int = int(month)
        sales_query = sales_query.filter(created_at__month=month_int)
        
        # Saber cuántos días tiene ese mes específico en ese año
        num_days = calendar.monthrange(int(year), month_int)[1]
        
        # Si quieren ver todo el mes detallado por días
        if week == 'all':
            labels = [f"Día {d}" for d in range(1, num_days + 1)]
            data = [0.0] * num_days
            
            daily_totals = sales_query.annotate(
                d=ExtractDay('created_at')
            ).values('d').annotate(total=Sum('total')).order_by('d')
            
            for item in daily_totals:
                if item['d'] and 1 <= item['d'] <= num_days:
                    data[item['d'] - 1] = float(item['total'])
                    
        # Si eligen una semana específica del mes (Bloques de 7 días)
        else:
            week_int = int(week)
            start_day = (week_int - 1) * 7 + 1
            end_day = week_int * 7 if week_int < 4 else num_days # La última semana toma hasta el final del mes
            
            sales_query = sales_query.filter(created_at__day__gte=start_day, created_at__day__lte=end_day)
            
            labels = [f"Día {d}" for d in range(start_day, end_day + 1)]
            data = [0.0] * len(labels)
            
            daily_totals = sales_query.annotate(
                d=ExtractDay('created_at')
            ).values('d').annotate(total=Sum('total')).order_by('d')
            
            for item in daily_totals:
                if item['d'] and start_day <= item['d'] <= end_day:
                    index = item['d'] - start_day
                    data[index] = float(item['total'])

    return JsonResponse({'labels': labels, 'data': data})

@login_required
def process_sale_api(request):
    """
    Recibe el carrito en formato JSON desde JavaScript, 
    crea la venta, descuenta el stock y registra el ingreso.
    """
    if request.method == 'POST':
        try:
            mi_tenant = request.user.tenantuser.tenant
            
            # 1. Leemos el JSON que nos manda el navegador
            data = json.loads(request.body)
            cart_items = data.get('cart', [])
            
            if not cart_items:
                return JsonResponse({'error': 'El carrito está vacío'}, status=400)

            # 2. Iniciamos la transacción segura
            with transaction.atomic():
                # Calculamos el total desde el backend por seguridad (nunca confíes en el total del frontend)
                subtotal = sum(float(item['price']) * int(item['quantity']) for item in cart_items)
                tax = subtotal * 0.16
                total_final = subtotal + tax
                
                # 3. Creamos el registro de la Venta general
                nueva_venta = Sale.objects.create(
                    tenant=mi_tenant,
                    total=total_final # Ajusta el nombre del campo si en tu modelo se llama diferente (ej. total_amount)
                )
                
                # 4. Procesamos cada producto del ticket
                for item in cart_items:
                    producto_db = Product.objects.get(id=item['id'], tenant=mi_tenant)
                    cantidad_vendida = int(item['quantity'])
                    
                    if producto_db.stock < cantidad_vendida:
                        raise Exception(f"Stock insuficiente para {producto_db.name}")
                        
                    # Descontamos el stock y guardamos
                    producto_db.stock -= cantidad_vendida
                    producto_db.save()
                    
                    # (Reemplaza tu comentario con esto)
                    SaleItem.objects.create(
                        sale=nueva_venta,
                        product=producto_db,
                        quantity=cantidad_vendida,
                        price_at_sale=item['price']
                    )
                
                # 5. Registramos la entrada de dinero
                FinancialMovement.objects.create(
                    tenant=mi_tenant,
                    sale=nueva_venta,
                    movement_category='venta', # La categoría que definimos hace unos días
                    amount=total_final, # Ajusta si tu modelo requiere 'amount' o 'description'
                )

            # Si todo salió bien, respondemos con éxito
            return JsonResponse({'message': 'Venta registrada con éxito'})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Método no permitido'}, status=405)


@login_required
def inventory_view(request):
    """
    Despliega todo el catálogo de productos del Tenant 
    y calcula las métricas del almacén.
    """
    mi_tenant = request.user.tenantuser.tenant
    all_products = Product.objects.filter(tenant=mi_tenant).order_by('name')
    
    # Calculamos cuántos productos tienen stock bajo en base a su propia alerta
    low_stock_count = 0
    for p in all_products:
        # Usamos un valor por defecto de 5 si min_stock_alert no está definido
        min_alerta = p.min_stock_alert if getattr(p, 'min_stock_alert', None) is not None else 5
        if p.stock <= min_alerta:
            low_stock_count += 1

    context = {
        'products': all_products,
        'total_products': all_products.count(),
        'low_stock_count': low_stock_count,
    }
    return render(request, 'inventory.html', context)


def register_tenant_view(request):
    """
    Vista pública para que cualquier usuario se registre, 
    cree su empresa y asigne su rubro.
    """
    # Si el usuario ya está logueado, lo mandamos directo al dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        try:
            # 1. Capturar datos del Formulario
            username = request.POST.get('email') # Usaremos el email como username
            email = request.POST.get('email')
            password = request.POST.get('password')
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            
            company_name = request.POST.get('company_name')
            business_type = request.POST.get('business_type') # El rubro (gym, barber, etc.)
            
            # 2. VALIDACIÓN BÁSICA: Verificar que el usuario no exista
            if User.objects.filter(username=username).exists():
                return render(request, 'register.html', {'error': 'Este correo ya está registrado.'})
            
            # 3. CREACIÓN EN CADENA (Transacción lógica)
            # Creación del usuario
            nuevo_usuario = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            
            # Creación de la empresa (Tenant) con su rubro
            # Nota: Si aún no agregas 'business_type' a tu modelo Tenant con migraciones,
            # puedes omitirlo aquí temporalmente o agregarlo a tu modelo.
            nueva_empresa = Tenant.objects.create(
                name=company_name,
                plan='basic' # Todos empiezan en el plan básico por defecto
            )
            
            # Enlace intermedio (TenantUser) asignándolo como Administrador de su entorno
            TenantUser.objects.create(
                user=nuevo_usuario,
                tenant=nueva_empresa,
                role='admin'
            )
            
            # 4. INICIO DE SESIÓN AUTOMÁTICO
            login(request, nuevo_usuario)
            
            # Redirección al Dashboard ya logueado
            return redirect('dashboard')
            
        except Exception as e:
            return render(request, 'register.html', {'error': f'Ocurrió un error en el registro: {str(e)}'})
            
    return render(request, 'register.html')

@login_required
def add_product(request):
    """
    Recibe los datos, autogenera el SKU y guarda el producto.
    """
    if request.method == 'POST':
        try:
            mi_tenant = request.user.tenantuser.tenant
            
            # 1. Recibimos los datos (ya no pedimos el SKU)
            name = request.POST.get('name')
            stock = request.POST.get('stock')
            price = request.POST.get('price')
            cost_price = request.POST.get('cost_price')
            
            # --- LÓGICA DE AUTO-SKU ---
            # 2. Contamos cuántos productos tiene la empresa para saber el número que sigue
            total_productos = Product.objects.filter(tenant=mi_tenant).count()
            siguiente_numero = total_productos + 1
            
            # 3. Tomamos las primeras 3 letras del nombre (ej. "Lam" de Lamina)
            prefijo = name[:3].upper() if name else "PRD"
            
            # 4. Armamos el SKU (Ej: LAM-0001)
            sku_generado = f"{prefijo}-{siguiente_numero:04d}"
            
            # 5. Guardamos en la base de datos
            Product.objects.create(
                tenant=mi_tenant,
                sku=sku_generado,
                name=name,
                stock=stock,
                sale_price=price,
                cost_price=cost_price,
            )
            print(f"Producto guardado exitosamente: {sku_generado}") # Para verlo en la terminal
            
        except Exception as e:
            # Si algo falla, lo imprimimos en la terminal en lugar de colgar el servidor
            print(f"¡Error crítico al guardar!: {str(e)}")
            
    # Redirigimos siempre al inventario
    return redirect('inventory')


@login_required
def dashboard_view(request):
    mi_tenant = request.user.tenantuser.tenant
    
    # Obtenemos la fecha actual
    hoy = timezone.now().date()
    
    # 1. Ventas de HOY
    ventas_hoy = Sale.objects.filter(
        tenant=mi_tenant, 
        created_at__date=hoy
    ).aggregate(total_vendido=Sum('total'))['total_vendido'] or 0.00

    # 2. Ventas del MES
    ventas_mes = Sale.objects.filter(
        tenant=mi_tenant,
        created_at__year=hoy.year,
        created_at__month=hoy.month
    ).aggregate(total_vendido=Sum('total'))['total_vendido'] or 0.00

    # 3. Ventas del AÑO
    ventas_anio = Sale.objects.filter(
        tenant=mi_tenant,
        created_at__year=hoy.year
    ).aggregate(total_vendido=Sum('total'))['total_vendido'] or 0.00

    context = {
        'ventas_hoy': ventas_hoy,
        'ventas_mes': ventas_mes,
        'ventas_anio': ventas_anio,
    }
    return render(request, 'dashboard.html', context)

@login_required
@csrf_exempt 
def api_chat(request):
    if request.method == 'POST':
        try:
            # Leemos el mensaje que mandó el Javascript desde el navegador
            data = json.loads(request.body)
            user_message = data.get('message', '')
            
            # Identificamos el inquilino por seguridad
            mi_tenant = request.user.tenantuser.tenant
            
            # 🧠 Llamamos al cerebro de la IA
            respuesta_ia = chat_with_agent(mi_tenant.id, mi_tenant.name, user_message)
            
            # Devolvemos la respuesta en formato JSON
            return JsonResponse({'reply': respuesta_ia})
        except Exception as e:
            return JsonResponse({'reply': f"Error en el servidor: {str(e)}"}, status=500)
            
    return JsonResponse({'error': 'Solo peticiones POST'}, status=400)

@login_required
def pos_view(request):
    """
    Despliega la interfaz del Punto de Venta (POS).
    Trae los productos del inquilino que tienen al menos 1 artículo en stock.
    """
    mi_tenant = request.user.tenantuser.tenant
    
    # Filtramos productos con stock mayor a cero (stock__gt=0)
    available_products = Product.objects.filter(tenant=mi_tenant, stock__gt=0).order_by('name')
    
    context = {
        'products': available_products,
    }
    return render(request, 'pos.html', context)