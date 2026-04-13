from rest_framework import serializers
from .models import User, Country


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'code', 'name')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label='Confirm password')

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'phone', 'country', 'password', 'password2')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    country_id = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        source='country',
        write_only=True,
        required=False,
        allow_null=True,
    )
    # role is read-only — cannot be self-assigned via API
    role = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'phone',
            'role', 'country', 'country_id',
            'date_joined', 'is_active',
        )
        read_only_fields = ('id', 'date_joined', 'is_active')
