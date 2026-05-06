# Food Delivery Backend API

Django REST API backend for a food delivery system with MySQL database.

## Features

- User authentication and authorization (Admin, Restaurant owners, Customers)
- Restaurant management with special/general restaurant types
- Product/Menu management with categories
- Order processing with real-time status updates
- Payment integration (QR Code, Bank Transfer)
- Review system for restaurants and products
- Notification system
- Search functionality with history
- Analytics for admin and restaurant owners
- Favorites management

## Requirements

- Python 3.8+
- MySQL 5.7+
- Django 4.2.7
- Django REST Framework 3.14.0

## Installation

1. Clone the repository:
```bash
cd Backend
```

2. Create a virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create MySQL database:
```sql
CREATE DATABASE food_delivery_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

5. Create `.env` file in the root directory:
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=food_delivery_db
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

6. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

7. Create superuser:
```bash
python manage.py createsuperuser

# สร้าง Default Settings
python manage.py create_default_settings
```

```bash
# ตรวจสอบ users ที่ยังไม่ได้ verify email
python manage.py fix_email_verification
```

8. Run the development server:
```bash
python manage.py runserver
```

## 📚 Documentation

### 🔗 Complete API Reference
- **[WORKING_ENDPOINTS.md](WORKING_ENDPOINTS.md)** - ✨ **Complete and up-to-date API documentation**
  - All endpoints with examples
  - Request/Response formats
  - Authentication methods
  - Error handling

### 📖 User Guides
- **[USER_MANUAL.md](USER_MANUAL.md)** - Complete user manual for all roles
- **[SECURITY_GUIDE.md](SECURITY_GUIDE.md)** - Security and authentication guide
- **[EMAIL_SETUP_GUIDE.md](EMAIL_SETUP_GUIDE.md)** - Email verification setup guide

## 🚀 Quick Start

1. **Start the server:**
   ```bash
   python manage.py runserver
   ```

2. **Browse API:**
   ```
   http://127.0.0.1:8000/api/
   ```

3. **Admin Panel:**
   ```
   http://127.0.0.1:8000/admin/
   ```

## 📁 Project Structure

```
Backend/
├── 📁 food_delivery_backend/    # Django settings
├── 📁 api/                      # Main API application  
├── 📁 accounts/                 # User management & authentication
├── 📁 venv/                     # Virtual environment
├── 📄 manage.py                 # Django management
├── 📄 requirements.txt          # Dependencies
├── 📄 food_delivery_schema.sql  # Database schema
├── 📄 README.md                 # This file
├── 📚 WORKING_ENDPOINTS.md      # Complete API documentation
├── 📚 USER_MANUAL.md            # User manual
├── 📚 SECURITY_GUIDE.md         # Security & authentication guide
└── 📚 EMAIL_SETUP_GUIDE.md      # Email verification setup
```

## 🔑 Authentication

The API uses Token Authentication. Include the token in headers:
```http
Authorization: Token your_token_here
```

Get token by:
1. **Register:** `POST /api/auth/register/`
2. **Login:** `POST /api/auth/login/`

## 📋 Key Endpoints

### 🔐 Authentication
```http
POST /api/auth/register/    # Register
POST /api/auth/login/       # Login
GET  /api/auth/me/          # Profile
```

### 🏪 Core Resources
```http
GET /api/restaurants/       # Restaurants
GET /api/categories/        # Categories  
GET /api/products/          # Products
GET /api/orders/            # Orders
```

### 🔍 Search & Discovery
```http
GET /api/search/?q=keyword  # Search
GET /api/restaurants/special/ # Special restaurants
GET /api/restaurants/nearby/  # Nearby restaurants
```

### ⭐ Reviews & Favorites
```http
GET /api/reviews/           # Restaurant reviews
GET /api/product-reviews/   # Product reviews
GET /api/favorites/         # User favorites
```

**For complete endpoint documentation, see [WORKING_ENDPOINTS.md](WORKING_ENDPOINTS.md)**

## 🧪 Testing

### API Testing
1. **Browser:** Visit `http://127.0.0.1:8000/api/`
2. **Admin Panel:** Visit `http://127.0.0.1:8000/admin/`
3. **Postman:** Use examples from WORKING_ENDPOINTS.md
4. **curl:** Use examples from API documentation

## 🛠️ Development

### Database Schema
See `food_delivery_schema.sql` for complete database structure.

### Adding New Endpoints
1. Create ViewSet in `api/views.py`
2. Add to router in `api/urls.py`
3. Update documentation
4. Test with `final_endpoint_verification.py`

## 📊 Features Overview

- ✅ **Authentication:** Token-based with role management
- ✅ **Restaurants:** CRUD with special restaurant types
- ✅ **Products:** Menu management with categories
- ✅ **Orders:** Full order lifecycle with status tracking
- ✅ **Payments:** Multiple payment methods
- ✅ **Reviews:** Restaurant and product reviews
- ✅ **Search:** Advanced search with history
- ✅ **Notifications:** Real-time user notifications
- ✅ **Analytics:** Dashboard for admins and restaurants
- ✅ **Favorites:** User favorites management

## 🤝 Contributing

1. Follow the existing code structure
2. Update documentation when adding features
3. Test all endpoints with the testing script
4. Ensure proper authentication handling

## 📞 Support

For questions or issues:
1. Check the documentation files
2. Run the endpoint testing script
3. Review the user manual
4. Check the API documentation

---

**📅 Last Updated:** June 20, 2025  
**🔄 Version:** 2.2 - Enhanced API documentation with user role specifications  
**🚀 Recent Updates:** 
- ✅ Fixed 405 Method Not Allowed errors (POST vs GET methods)
- ✅ Fixed 404 Not Found errors (user permission issues)
- ✅ Added comprehensive troubleshooting documentation
- ✅ Added user role specifications to all API endpoints
- ✅ Enhanced documentation with clear permission guidelines # food_delivery_asean_mall
# asean_mall_food_delivery
# taca
# taca
