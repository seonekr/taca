from pathlib import Path
from decouple import config
import os
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'


_env_hosts = os.environ.get('ALLOWED_HOSTS')
# If not specified, allow all hosts (useful for internal LB health checks)
ALLOWED_HOSTS = _env_hosts.split(',') if _env_hosts else ['*']

# CORS configuration
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:3030',
    'http://localhost:5173',
    'http://127.0.0.1:3000',
    'http://127.0.0.1:3030',
    'http://127.0.0.1:5173',
    'https://matjyp.com',
]

# CSRF configuration for API
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:3030',
    'http://localhost:5173',
    'http://127.0.0.1:3000',
    'http://127.0.0.1:3030',
    'http://127.0.0.1:5173',
    'http://localhost:8000',
    'https://matjyp.com',
]

CORS_ALLOW_CREDENTIALS = True

# Allow all origins for development only
CORS_ALLOW_ALL_ORIGINS = DEBUG

# Allow specific headers
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Exempt API endpoints from CSRF
CSRF_EXEMPT_URLS = [
    r'^/api/',
]

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_filters',
    'channels',
    'storages',
    
    # Local apps
    'accounts',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'taca_backend.middleware.DisableCSRFMiddleware',  # Disable CSRF for API endpoints
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'taca_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'taca_backend.wsgi.application'

# ASGI application (used by Daphne for WebSocket)
ASGI_APPLICATION = 'taca_backend.asgi.application'

# Channel layers (using in-memory for development, Redis for production)
if DEBUG:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
else:
    # Redis for production
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [('127.0.0.1', 6379)],
            },
        },
    }


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',  # Using mysql-connector-python instead of mysqlclient
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'use_unicode': True,
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Bangkok'

USE_I18N = False

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

if not DEBUG:
    # aws settings
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_VERIFY = True
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    STATICFILES_STORAGE = "storages.backends.s3boto3.S3StaticStorage"
    AWS_S3_CUSTOM_DOMAIN = (
        f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com"
    )
    STATIC_LOCATION = "static"
    STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{STATIC_LOCATION}/"
    PUBLIC_MEDIA_LOCATION = "media"
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{PUBLIC_MEDIA_LOCATION}/"
else:
    # local settings
    STATIC_URL = "/static/"
    STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
    MEDIA_URL = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'taca_backend.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': 12,
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
}

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Email verification settings
REQUIRE_EMAIL_VERIFICATION = os.environ.get('REQUIRE_EMAIL_VERIFICATION', 'False').lower() == 'true'

# Email configuration
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND')
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'False').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL')

# Frontend URL for email links
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Base URL for API responses (used for image URLs)
BASE_URL = os.environ.get('BASE_URL')

# Routing distance provider (used for real road distance delivery fee calculation)
ROUTING_OSRM_BASE_URL = os.environ.get('ROUTING_OSRM_BASE_URL', 'https://router.project-osrm.org')
ROUTING_OSRM_TIMEOUT_SECONDS = int(os.environ.get('ROUTING_OSRM_TIMEOUT_SECONDS', 8))
ROUTING_DISTANCE_CACHE_TTL_SECONDS = int(os.environ.get('ROUTING_DISTANCE_CACHE_TTL_SECONDS', 1800))
ROUTING_COORD_PRECISION = int(os.environ.get('ROUTING_COORD_PRECISION', 5))

# Nominatim geocoding proxy tuning
NOMINATIM_BASE_URL = os.environ.get('NOMINATIM_BASE_URL', 'https://nominatim.openstreetmap.org')
NOMINATIM_TIMEOUT_SECONDS = int(os.environ.get('NOMINATIM_TIMEOUT_SECONDS', 8))
NOMINATIM_CACHE_TTL_SECONDS = int(os.environ.get('NOMINATIM_CACHE_TTL_SECONDS', 86400))
NOMINATIM_USER_AGENT = os.environ.get(
    'NOMINATIM_USER_AGENT',
    'FoodDeliveryAseanMall/1.0 (local geocoding proxy)'
)
NOMINATIM_MIN_INTERVAL_SECONDS = float(os.environ.get('NOMINATIM_MIN_INTERVAL_SECONDS', 1.1))
NOMINATIM_RETRY_BACKOFF_SECONDS = float(os.environ.get('NOMINATIM_RETRY_BACKOFF_SECONDS', 2.0))
NOMINATIM_RETRY_ATTEMPTS = int(os.environ.get('NOMINATIM_RETRY_ATTEMPTS', 1))
NOMINATIM_REVERSE_CACHE_PRECISION = int(os.environ.get('NOMINATIM_REVERSE_CACHE_PRECISION', 4))
NOMINATIM_RATE_LIMIT_COOLDOWN_SECONDS = int(os.environ.get('NOMINATIM_RATE_LIMIT_COOLDOWN_SECONDS', 30))

# Google OAuth configuration
GOOGLE_OAUTH2_CLIENT_ID = os.environ.get('GOOGLE_OAUTH2_CLIENT_ID')
GOOGLE_OAUTH2_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH2_CLIENT_SECRET')

# Security settings for production
if not DEBUG:
    # HTTPS Security
    # ปิด SSL redirect เพราะ Load Balancer จัดการ HTTPS แล้ว
    SECURE_SSL_REDIRECT = False  # เปลี่ยนจาก True เป็น False
    # Allow load-balancer health check over plain HTTP (no redirect to HTTPS)
    SECURE_REDIRECT_EXEMPT = [r'^api/health/$']
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Cookie Security
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Tell Django to trust the X-Forwarded-Proto header from load balancer
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Allow Load Balancer to send requests with different Host headers
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
