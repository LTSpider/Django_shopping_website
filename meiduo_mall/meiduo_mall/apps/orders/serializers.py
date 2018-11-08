from django_redis import get_redis_connection
from rest_framework import serializers
from django.db import transaction
from decimal import Decimal

from rest_framework.exceptions import ValidationError, APIException

from carts.serializers import CartSKUSerializer
from verifications.serializers import logger
from .models import OrderInfo, OrderGoods
from django.utils import timezone
from goods.models import SKU


class OrderSettlementSerializer(serializers.Serializer):
    # max_digits 包含小数的最多位数，decimal_places 几位小数  12345123.45
    freight = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    skus = CartSKUSerializer(many=True, read_only=True)


class SaveOrderSerializer(serializers.ModelSerializer):
    """保存订单的序列化器"""
    class Meta:
        model = OrderInfo
        fields = ('order_id', 'address', 'pay_method')

        # 'write_only':   向后端写数据  向后端传数据
        # 'read_only':  前端要从后端读取数据，后端返回数据使用
        read_only_fields = ('order_id',)
        extra_kwargs = {
            'address': {
                'write_only': True,
                'required': True
            },
            'pay_method': {
                'write_only': True,
                'required': True
            }
        }

    def create(self, validated_data):
        redis_conn = get_redis_connection("default")

        user = self.context['request'].user

        # 组织订单信息 20170903153611+user.id
        order_id = timezone.now().strftime('%Y%m%d%H%M%S') + ('%09d' % user.id)

        # 生成订单
        with transaction.atomic():
            # 创建一个保存点
            save_id = transaction.savepoint()

            try:
                # 创建订单信息
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=validated_data['address'],
                    total_count=0,
                    total_amount=Decimal(0),
                    freight=Decimal(10),
                    pay_method=validated_data['pay_method'],
                    status=OrderInfo.ORDER_STATUS_ENUM['UNSEND'] if validated_data['pay_method'] ==
                                                                    OrderInfo.PAY_METHODS_ENUM['CASH'] else
                    OrderInfo.ORDER_STATUS_ENUM['UNPAID']
                )
                # 获取购物车信息
                redis_conn = get_redis_connection('cart')
                redis_cart = redis_conn.hgetall("cart_%s" % user.id)
                cart_selected = redis_conn.smembers('cart_selected_%s' % user.id)
                # 将bytes类型转换为int类型
                cart = {}
                for sku_id in cart_selected:
                    cart[int(sku_id)] = int(redis_cart[sku_id])

                total_amount = Decimal("0")
                total_count = 0

                # skus = SKU.objects.filter(id__in=cart.keys())
                sku_id_list = cart.keys()

                # 处理订单商品
                for sku_id in sku_id_list:
                    # 出现对于同一个商品的争抢下单时，如失败，再次尝试，直到库存不足
                    while True:
                        sku = SKU.objects.get(id=sku_id)
                        sku_count = cart[sku.id]

                        # 判断库存
                        origin_stock = sku.stock  # 原始库存
                        origin_sales = sku.sales  # 原始销量

                        if sku_count > origin_stock:
                            transaction.savepoint_rollback(save_id)
                            raise ValidationError({'detail': '商品库存不足'})

                        # 减少库存
                        new_stock = origin_stock - sku_count
                        new_sales = origin_sales + sku_count

                        # 根据原始库存条件更新，返回更新的条目数，乐观锁
                        ret = SKU.objects.filter(id=sku.id, stock=origin_stock).update(stock=new_stock, sales=new_sales)
                        if ret == 0:
                            continue

                        sku.goods.sales += sku_count
                        sku.goods.save()

                        sku_amount = sku.price * sku_count  # 商品金额
                        total_amount += sku_amount  # 累计总金额
                        total_count += sku_count  # 累计总额

                        # 保存订单商品
                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=sku_count,
                            price=sku.price,
                        )

                        # 更新成功
                        break

                # 更新订单的金额数量信息
                order.total_amount = total_amount
                order.total_amount += order.freight
                order.total_count = total_count
                order.save()

            except ValidationError:
                raise
            except Exception as e:
                logger.error(e)
                transaction.savepoint_rollback(save_id)
                raise APIException('保存订单失败')

            # 提交事务
            transaction.savepoint_commit(save_id)

            # 更新redis中保存的购物车数据
            pl = redis_conn.pipeline()
            pl.hdel('cart_%s' % user.id, *cart_selected)
            pl.srem('cart_selected_%s' % user.id, *cart_selected)
            pl.execute()
            return order






















