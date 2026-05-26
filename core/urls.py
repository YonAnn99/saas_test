from django.contrib import admin
from django.urls import path
from erp.views import (
    dashboard_view, api_chat, add_product, register_tenant_view,
    inventory_view, pos_view, process_sale_api, sales_chart_api,
    purchases_view, create_purchase_order_api
)
from erp.stripe_views import (
    pricing_view, create_checkout_session,
    checkout_success, customer_portal, stripe_webhook, redeem_promo_code
)
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',               dashboard_view,          name='dashboard'),
    path('inventario/',    inventory_view,           name='inventory'),
    path('ventas/',        pos_view,                 name='pos'),
    path('compras/',       purchases_view,           name='purchases'),
    path('register/',      register_tenant_view,     name='register_tenant'),
    path('login/',         auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('api/chat/',              api_chat,                 name='api_chat'),
    path('add_product/',           add_product,              name='add_product'),
    path('api/process_sale/',      process_sale_api,         name='process_sale_api'),
    path('api/sales_chart/',       sales_chart_api,          name='sales_chart_api'),
    path('compras/registrar-orden/', create_purchase_order_api, name='create_purchase_order'),
    path('planes/',                        pricing_view,             name='pricing'),
    path('planes/checkout/<str:price_id>/', create_checkout_session, name='create_checkout'),
    path('planes/exito/',                  checkout_success,         name='checkout_success'),
    path('planes/portal/',                 customer_portal,          name='customer_portal'),
    path('stripe/webhook/',                stripe_webhook,           name='stripe_webhook'),
    path('planes/canjear/',                redeem_promo_code,        name='redeem_promo_code'),
]