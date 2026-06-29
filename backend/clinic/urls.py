from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('appointments/', views.book_appointment, name='book_appointment'),
]
