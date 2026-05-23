from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import InviteCode, EmailVerifyCode


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label='邮箱',
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': '用于接收验证码'}),
    )
    email_code = forms.CharField(
        label='邮箱验证码',
        max_length=8,
        widget=forms.TextInput(attrs={'placeholder': '6 位数字', 'autocomplete': 'off'}),
    )
    invite_code = forms.CharField(
        label='邀请码（可选）',
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '填了即送会员天数'}),
    )

    class Meta:
        model  = User
        fields = ['username', 'email', 'email_code', 'password1', 'password2', 'invite_code']

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('该邮箱已被注册')
        return email

    def clean_invite_code(self):
        code = self.cleaned_data.get('invite_code', '').strip().upper()
        if not code:
            return ''
        try:
            invite = InviteCode.objects.get(code=code)
        except InviteCode.DoesNotExist:
            raise forms.ValidationError('邀请码不存在')
        if not invite.is_usable:
            raise forms.ValidationError('邀请码已被使用或已失效')
        self._invite = invite
        return code

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get('email')
        code  = (cleaned.get('email_code') or '').strip()
        if email and code:
            record = EmailVerifyCode.latest_for(email)
            if not record or record.code != code:
                self.add_error('email_code', '验证码错误')
            elif not record.is_usable:
                self.add_error('email_code', '验证码已过期，请重新获取')
            else:
                self._email_code_record = record
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            if getattr(self, '_email_code_record', None):
                self._email_code_record.consume()
            if getattr(self, '_invite', None):
                self._invite.redeem(user)
        return user


class RedeemCodeForm(forms.Form):
    code = forms.CharField(
        label='邀请码',
        max_length=32,
        widget=forms.TextInput(attrs={'placeholder': '输入邀请码续期'}),
    )

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip().upper()
        try:
            invite = InviteCode.objects.get(code=code)
        except InviteCode.DoesNotExist:
            raise forms.ValidationError('邀请码不存在')
        if not invite.is_usable:
            raise forms.ValidationError('邀请码已被使用或已失效')
        self._invite = invite
        return code
