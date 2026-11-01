# Inventory & Order Management System

A Django REST Framework backend for managing product catalogs, inventory movements, customer orders, and business reports using PostgreSQL.

## Features

- Product, category, and supplier management
- Inventory stock-in, stock-out, and stock adjustments
- Inventory movement history and audit trail
- Low-stock and out-of-stock reports
- Order creation, item pricing, and automatic stock deduction
- Order cancellation with stock restoration
- Transaction-safe stock operations and concurrency protection
- Token authentication and role-based permissions
- Order ownership restrictions
- Inventory valuation and sales reports
- Filtering, searching, and ordering
- Interactive Swagger API documentation

## Technology Stack

- Python 3.12
- Django 5.2
- Django REST Framework
- PostgreSQL
- django-filter
- drf-spectacular / OpenAPI

## Requirements

- Python 3.12 or compatible version
- PostgreSQL
- Git

## Setup on Windows

### 1. Clone the repository

```powershell
git clone YOUR_GITHUB_REPOSITORY_URL
cd inventory-management
```

### 2. Create and activate a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure PostgreSQL

Create a PostgreSQL database named `inventory_management`.

Configure the following environment variables in PowerShell.
Use your own secret key and PostgreSQL password; never commit them.

```powershell
$env:DJANGO_SECRET_KEY = "YOUR_PRIVATE_DJANGO_SECRET_KEY"
$env:DJANGO_DEBUG = "True"
$env:DB_PASSWORD = "YOUR_POSTGRES_PASSWORD"
```

For local development, generate a secret key using:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the generated value as `DJANGO_SECRET_KEY`.

### 5. Apply database migrations

```powershell
python manage.py migrate
```

### 6. Create an administrator

```powershell
python manage.py createsuperuser
```

### 7. Start the development server

```powershell
python manage.py runserver
```

## API Documentation

With the server running:

- Swagger UI: http://127.0.0.1:8000/api/docs/
- OpenAPI schema: http://127.0.0.1:8000/api/schema/
- Django admin: http://127.0.0.1:8000/admin/

## Authentication

The API uses Django REST Framework token authentication.

Obtain a token through the configured authentication endpoint, then include it in requests:

`Authorization: Token YOUR_TOKEN`

Authenticated users can access permitted read operations. Staff permissions are required for administrative operations, and order access is restricted according to ownership and staff privileges.

## Main API Routes

| Area | Endpoint |
| --- | --- |
| Products | `/api/products/` |
| Product details | `/api/products/<id>/` |
| Inventory movements | `/api/inventory/movements/` |
| Stock in | `/api/inventory/stock-in/` |
| Stock out | `/api/inventory/stock-out/` |
| Low-stock report | `/api/inventory/reports/low-stock/` |
| Out-of-stock report | `/api/inventory/reports/out-of-stock/` |
| Inventory valuation | `/api/inventory/reports/valuation/` |
| Orders | `/api/orders/` |
| Order details | `/api/orders/<id>/` |
| Cancel order | `/api/orders/<id>/cancel/` |
| Order summary | `/api/orders/reports/summary/` |
| Daily sales | `/api/orders/reports/daily-sales/` |
| Product performance | `/api/orders/reports/product-performance/` |

## Running Tests

Run the application tests with:

```powershell
python manage.py test inventory orders catalog
```

The project's test suite has previously passed 75 tests, including inventory, order processing, permissions, transaction rollback, and concurrent order creation.

## Engineering Notes

- Order totals are calculated on the server.
- Purchase-time prices are saved on order items.
- Database transactions protect related order and inventory updates.
- Stock movements maintain an inventory audit trail.
- PostgreSQL row locking is used for concurrent stock operations.

## Security

This repository must not contain real secret keys, database passwords, `.env` files, or production credentials.

Before deployment, configure `DEBUG=False`, appropriate `ALLOWED_HOSTS`, secure environment variables, HTTPS, and Django's production security settings.

## License

No license has been selected yet.
