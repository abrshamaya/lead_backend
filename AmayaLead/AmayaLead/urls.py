"""
URL configuration for AmayaLead project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.urls import path, include
from amaya_api import auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('amaya_api.urls')),
    path('api/auth/login', auth_views.login, name='auth-login'),
    path('api/auth/refresh', auth_views.refresh_token, name='auth-refresh'),
    path('api/auth/me', auth_views.me, name='auth-me'),
    path('api/auth/change-password', auth_views.change_password, name='auth-change-password'),
    path('api/auth/forgot-password', auth_views.forgot_password, name='auth-forgot-password'),
    path('api/auth/reset-password', auth_views.reset_password, name='auth-reset-password'),
    path('api/auth/users', auth_views.users, name='auth-users'),
    path('api/auth/users/<int:user_id>', auth_views.user_detail, name='auth-user-detail'),
]
