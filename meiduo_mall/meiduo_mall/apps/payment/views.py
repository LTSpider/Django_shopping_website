import os

from alipay import AliPay
from django.conf import settings
from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import OrderInfo
from payment.models import Payment


class PaymentView(APIView):
    """
    支付
    /orders/(?P<order_id>\d+)/payment/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        """
        获取支付链接
        """
        # 判断订单信息是否正确

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=request.user, status=OrderInfo.ORDER_STATUS_ENUM["UNPAID"])
        except OrderInfo.DoesNotExist:
            return Response({'message': '订单信息有误'}, status=status.HTTP_400_BAD_REQUEST)

        # 构造支付宝支付链接地址
        alipay_client = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys/app_private_key.pem"),
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys/alipay_public_key.pem"),  # 支付宝的公钥, 验证支付宝回传消息使用, 不是你自己的公钥
            sign_type="RSA2",  # SRA或者SRA2
            debug=settings.ALIPAY_DEBUG  # 默认False
        )

        order_string = alipay_client.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=str(order.total_amount),
            subject="美多商城%s" % order_id,
            return_url="http://www.meiduo.site:8080/pay_success.html",
        )

        # 需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        # 拼接链接返回前端
        alipay_url = settings.ALIPAY_GATEWAY_URL + '?' + order_string

        return Response({'alipay_url': alipay_url})

class PaymentStatusView(APIView):
    """
    支付结果
    """

    def put(self, request):
        # 把Django字典, 转换为python字典
        data = request.query_params.dict()
        signature = data.pop("sign")

        # 构造支付宝支付链接地址
        alipay_client = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys/app_private_key.pem"),
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                "keys/alipay_public_key.pem"),  # 支付宝的公钥, 验证支付宝回传消息使用, 不是你自己的公钥
            sign_type="RSA2",  # SRA或者SRA2
            debug=settings.ALIPAY_DEBUG  # 默认False
        )

        success = alipay_client.verify(data, signature)

        if success:
            # 订单编号
            order_id = data.get('out_trade_no')
            # 支付宝支付流水号
            trade_id = data.get('trade_no')

            # 保存支付数据
            # 修改订单数据
            Payment.objects.create(
                order_id=order_id,
                trade_id=trade_id
            )
            OrderInfo.objects.filter(order_id=order_id, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID']).update(status=OrderInfo.ORDER_STATUS_ENUM['UNSEND'])
            return Response({"trade_id": trade_id})
        else:
            # 参数据不是支付宝的，是非法请求
            return Response({'message': '参数错误'}, status=status.HTTP_403_FORBIDDEN)