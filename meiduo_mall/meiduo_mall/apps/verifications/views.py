import random
from django.http.response import HttpResponse
from django_redis import get_redis_connection
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from celery_tasks.sms.tasks import send_sms_code
from meiduo_mall.libs.yuntongxun.sms import CCP
from meiduo_mall.libs.captcha.captcha import captcha
from users.models import User
from . import serializers
from . import constants

# Create your views here.
class ImageCodeView(APIView):
    """
    图片验证码
    """
    def get(self, request, image_code_id):

        # 生成验证码图片
        text, image = captcha.generate_captcha()

        # 获取redis的连接对象
        redis_conn = get_redis_connection("verify_codes")
        redis_conn.setex("img_%s" % image_code_id, constants.IMAGE_CODE_REDIS_EXPIRES, text)

        print(text)

        return HttpResponse(image, content_type="images/jpg")


class SmsCodeView(GenericAPIView):
    """
    创建短信验证码
    """
    serializer_class = serializers.CheckImageCodeSerializer

    def get(self, request, mobile):
        """
        校验图片验证码和发送短信的频次
        mobile是被放到了类视图对象属性kwaargs中
        """
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        # 校验通过
        # 生成短信验证码
        sms_code = "%06d" % random.randint(0, 999999)
        print(sms_code)
        # 保存短信验证码与发送记录
        redis_conn = get_redis_connection('verify_codes')

        # 保存验证码及发送记录
        # 使用redis的pipeline管道一次执行多条命令
        pl = redis_conn.pipeline()
        pl.setex("sms_%s" % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        pl.setex("send_flag_%s" % mobile, constants.SEND_SMS_CODE_INTERVAL, 1)

        # 让管道执行命令
        pl.execute()

        # 发送短信验证码
        # ccp = CCP()
        # time = str(constants.SMS_CODE_REDIS_EXPIRES // 60)
        # ccp.send_template_sms(mobile, [sms_code, time], constants.SMS_CODE_TEMP_ID)
        # 使用celery发布异步任务
        send_sms_code.delay(mobile, sms_code)

        # 返回
        return Response({"message": "OK"})


class SmsCodeByTokenView(APIView):
    """根据access_token发送短信"""
    def get(self, request):
        # 获取并校验access_token
        access_token = request.query_params.get('access_token')
        if not access_token:
            return Response({"message":"缺少acces_token "}, status=status.HTTP_400_BAD_REQUEST)

        # 从access_token取出手机号
        mobile = User.check_send_sms_code_token(access_token)
        if mobile is None:
            return Response({"message": "无效的access_token"}, status=status.HTTP_400_BAD_REQUEST)

        # 判断手机号发送的次数
        redis_conn = get_redis_connection('verify_codes')
        send_flag = redis_conn.get("send_flag_%s" % mobile)
        if send_flag:
            return Response({"message":"发送短信次数过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # 生成短信验证码
        sms_code = "%06d" % random.randint(0, 999999)
        print(sms_code)
        # 保存短信验证码与发送记录
        # redis_conn.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        # redis_conn.setex('send_flag_%s' % mobile, contants.SEND_SMS_CODE_INTERVAL, 1)

        # 保存验证码及发送记录
        # 使用redis的pipeline管道一次执行多条命令
        pl = redis_conn.pipeline()
        pl.setex("sms_%s" % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        pl.setex("send_flag_%s" % mobile, constants.SEND_SMS_CODE_INTERVAL, 1)

        # 让管道执行命令
        pl.execute()

        # 发送短信验证码
        # ccp = CCP()
        # time = str(constants.SMS_CODE_REDIS_EXPIRES // 60)
        # ccp.send_template_sms(mobile, [sms_code, time], constants.SMS_CODE_TEMP_ID)
        # 使用celery发布异步任务
        send_sms_code.delay(mobile, sms_code)

        # 返回
        return Response({"message": "OK"})


