from django.contrib import admin
from .models import Tenant, TenantUser, Customer, Product, Sale, SaleItem, FinancialMovement

# Registramos los modelos para que aparezcan en el panel visual
admin.site.register(Tenant)
admin.site.register(TenantUser)
admin.site.register(Customer)
admin.site.register(Product)
admin.site.register(Sale)
admin.site.register(SaleItem)
admin.site.register(FinancialMovement)