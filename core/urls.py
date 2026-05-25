"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from erp.views import dashboard_view
from erp.views import api_chat
from erp.views import add_product
from erp.views import register_tenant_view
from django.contrib.auth import views as auth_views
from erp.views import inventory_view , pos_view , process_sale_api,sales_chart_api,purchases_view, create_purchase_order_api


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard_view, name='dashboard'),
    path('api/chat/', api_chat, name='api_chat'),
    path('add_product/', add_product, name='add_product'),
    path('register/' , register_tenant_view, name='register_tenant'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('inventario/' , inventory_view, name='inventory'),
    path('ventas/' , pos_view, name='pos'),
    path('api/process_sale/', process_sale_api, name='process_sale_api'),
    path('api/sales_chart/', sales_chart_api, name='sales_chart_api'),
    path('compras/' , purchases_view, name='purchases'),
    path('compras/registrar-orden/' , create_purchase_order_api, name='create_purchase_order'),


]
