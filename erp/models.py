from django.db import models
from django.contrib.auth.models import User

# ==========================================
# 1. NÚCLEO MULTI-INQUILINO (TENANT)
# ==========================================
class Tenant(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    plan = models.CharField(max_length=20, default='basic')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class TenantUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='users')
    role = models.CharField(max_length=20, default='employee')

    def __str__(self):
        return f"{self.user.username} - {self.tenant.name}"

# ==========================================
# 2. MÓDULO DE CLIENTES (CRM)
# ==========================================
class Customer(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'email')

    def __str__(self):
        return self.name

# ==========================================
# 3. MÓDULO DE INVENTARIOS
# ==========================================
class Product(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    sku = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    stock = models.IntegerField(default=0)
    min_stock_alert = models.IntegerField(default=5)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'sku')

    def __str__(self):
        return f"[{self.sku}] {self.name} - Stock: {self.stock}"

# ==========================================
# 4. MÓDULO DE FINANZAS Y VENTAS
# ==========================================
class Sale(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Venta #{self.id} - {self.customer.name}"

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

class FinancialMovement(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True)
    movement_type = models.CharField(max_length=10) # 'income' o 'expense'
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    due_date = models.DateField(null=True, blank=True)
    is_cleared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.movement_type.upper()} - ${self.amount}"