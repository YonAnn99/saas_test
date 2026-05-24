import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Product, Customer, Sale
from django.http import JsonResponse
from .ai_agent import chat_with_agent
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required


@login_required(login_url='/admin/login/')
def dashboard_view(request):
    
    mi_tenant = request.user.tenantuser.tenant
    
    
    total_products = Product.objects.filter(tenant=mi_tenant).count()
    total_customers = Customer.objects.filter(tenant=mi_tenant).count()
    
    recent_products = Product.objects.filter(tenant=mi_tenant).order_by('-created_at')[:5]
    
    context = {
        'total_products': total_products,
        'total_customers': total_customers,
        'recent_products': recent_products,
        'nombre_empresa': mi_tenant.name, 
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