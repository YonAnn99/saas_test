from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# ==========================================
# 1. NÚCLEO MULTI-INQUILINO (TENANT)
# ==========================================
class Tenant(models.Model):
    PLAN_CHOICES = [
        ('basic', 'Básico - Gratis'),
        ('pro', 'Pro - $499/mes'),
        ('enterprise', 'Enterprise - $999/mes'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='basic')
    created_at = models.DateTimeField(auto_now_add=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    # Campos de Stripe
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name

    @property
    def is_pro(self):
        if self.trial_ends_at and self.trial_ends_at > timezone.now():
            return True
            
        # 2. Si no tiene demo o ya expiró, checamos si realmente está pagando
        return self.plan in ('pro', 'enterprise')


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
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'email'], name='unique_tenant_email')
        ]

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
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'sku'], name='unique_tenant_sku')
        ]

    def __str__(self):
        return f"[{self.sku}] {self.name} - Stock: {self.stock}"


# ==========================================
# 4. MÓDULO DE FINANZAS Y VENTAS
# ==========================================
class Sale(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        customer_name = self.customer.name if self.customer else "Sin cliente"
        return f"Venta #{self.id} - {customer_name}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"


class FinancialMovement(models.Model):
    CATEGORY_CHOICES = [
        ('venta', 'Venta Directa'),
        ('gasto', 'Gasto Operativo'),
        ('nomina', 'Pago de Nómina'),
        ('proveedor', 'Pago a Proveedores'),
        ('ajuste', 'Ajuste de Inventario'),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True)
    movement_type = models.CharField(max_length=10)
    movement_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='venta')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    due_date = models.DateField(null=True, blank=True)
    is_cleared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.movement_type.upper()} - ${self.amount}"


# ==========================================
# 5. MÓDULO DE COMPRAS Y PROVEEDORES
# ==========================================
class Supplier(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente de Recepción'),
        ('received', 'Mercancía Recibida'),
        ('cancelled', 'Cancelada'),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Orden #{self.id} - {self.supplier.name if self.supplier else 'Sin Proveedor'}"


class PurchaseItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"