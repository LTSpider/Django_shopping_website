from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()
router.register(r'areas', views.AreasViewSet, base_name='areas')

urlpatterns = [
    # url('', include(router.urls))
]

urlpatterns += router.urls