from rest_framework.generics import ListAPIView
from rest_framework_extensions.cache.mixins import ListCacheResponseMixin
from rest_framework.filters import OrderingFilter
from drf_haystack.viewsets import HaystackViewSet

from .serializers import SKUSerializer, SKUIndexSerializer
from .models import SKU
from . import constants

class HotSKUListViews(ListCacheResponseMixin, ListAPIView):
    """
    热销商品, 使用缓存扩展
    """
    serializer_class = SKUSerializer
    pagination_class = None

    def get_queryset(self):
        category_id = self.kwargs['category_id']
        return SKU.objects.filter(category_id=category_id, is_launched=True).order_by('-sales')[:constants.HOT_SKUS_COUNT_LIMIT]


class SKUSearchViewSet(HaystackViewSet):
    """
    SKU搜索
    """
    index_models = [SKU]

    serializer_class = SKUIndexSerializer


class SUKListView(ListAPIView):
    """
    ｓku商品列表数据
    """
    serializer_class = SKUSerializer
    # 通过定义过滤后端, 来实行排序行为
    filter_backends = (OrderingFilter,)
    ordering_fields = ('create_time', 'price', 'sales')

    def get_queryset(self):
        category_id = self.kwargs.get("category_id")
        print(category_id)
        return SKU.objects.filter(category_id=category_id, is_launched=True)