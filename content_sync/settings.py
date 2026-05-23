import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 从项目根的 .env 读取环境变量(若存在),不引入额外依赖
_env_path = BASE_DIR / '.env'
if _env_path.exists():
    for _line in _env_path.read_text(encoding='utf-8').splitlines():
        _line = _line.strip()
        if not _line or _line.startswith('#') or '=' not in _line:
            continue
        _k, _v = _line.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-insecure-do-not-use-in-prod')

DEBUG = os.environ.get('DJANGO_DEBUG', '').lower() in ('1', 'true', 'yes')

ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = ['https://bddog.cn', 'https://www.bddog.cn', 'http://47.90.153.73']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'posts',
    'accounts',
    'wolfsheep',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'content_sync.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'content_sync.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 6},
    },
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_MODEL   = os.environ.get('DEEPSEEK_MODEL',   'deepseek-chat')

BOCHA_API_KEY    = os.environ.get('BOCHA_API_KEY',    '')
BOCHA_SEARCH_URL = 'https://api.bochaai.com/v1/web-search'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

QWGUA_MCH_ID   = os.environ.get('QWGUA_MCH_ID',   '')
QWGUA_MCH_KEY  = os.environ.get('QWGUA_MCH_KEY',  '')
QWGUA_BASE     = os.environ.get('QWGUA_BASE',     'https://pay.pp.qwgua.com')
QWGUA_PAY_CODES = {
    'wechat': os.environ.get('QWGUA_CODE_WECHAT', '1999'),  # 微信原生VPN，6%
    'alipay': os.environ.get('QWGUA_CODE_ALIPAY', '1888'),  # 支付宝原生VPN，6%
    'test':   os.environ.get('QWGUA_CODE_TEST',   '0000'),  # 内置测试，0%
}
QWGUA_NOTIFY_URL = os.environ.get('QWGUA_NOTIFY_URL', 'https://bddog.cn/accounts/pay/notify/')
QWGUA_RETURN_URL = os.environ.get('QWGUA_RETURN_URL', 'https://bddog.cn/accounts/pay/return/')

EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = os.environ.get('ALIYUN_SMTP_HOST', 'smtpdm.aliyun.com')
EMAIL_PORT          = int(os.environ.get('ALIYUN_SMTP_PORT', '465'))
EMAIL_USE_SSL       = True
EMAIL_HOST_USER     = os.environ.get('ALIYUN_SMTP_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('ALIYUN_SMTP_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL', '小菜鸡仓库 <noreply@bddog.cn>')
