from rest_framework import serializers
from .models import Currency, Category, Transaction, Budget


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ('id', 'code', 'name', 'symbol')


class CategorySerializer(serializers.ModelSerializer):
    # is_default is read-only — only settable via admin/fixtures
    is_default = serializers.BooleanField(read_only=True)
    # Expose owner username for readability; hide internals
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Category
        fields = ('id', 'name', 'category_type', 'user', 'is_default', 'icon', 'color')

    def validate_category_type(self, value):
        if value not in ('income', 'expense'):
            raise serializers.ValidationError("category_type must be 'income' or 'expense'.")
        return value


class TransactionSerializer(serializers.ModelSerializer):
    # Nested reads — return full objects for display
    category = CategorySerializer(read_only=True)
    currency = CurrencySerializer(read_only=True)

    # Write via FK ids
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True,
        required=False,
        allow_null=True,
    )
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(),
        source='currency',
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Transaction
        fields = (
            'id', 'title', 'note', 'amount',
            'transaction_type', 'category', 'category_id',
            'currency', 'currency_id',
            'date', 'attachment', 'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def validate(self, data):
        # Ensure transaction_type matches category type when a category is set
        category = data.get('category') or (self.instance.category if self.instance else None)
        transaction_type = data.get('transaction_type') or (self.instance.transaction_type if self.instance else None)
        if category and transaction_type and category.category_type != transaction_type:
            raise serializers.ValidationError(
                f"Category '{category.name}' is of type '{category.category_type}' "
                f"but transaction is '{transaction_type}'."
            )
        return data


class BudgetSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer(read_only=True)
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(),
        source='currency',
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Budget
        fields = ('id', 'amount_limit', 'currency', 'currency_id', 'start_date', 'end_date')
        read_only_fields = ('id',)

    def validate(self, data):
        start = data.get('start_date') or (self.instance.start_date if self.instance else None)
        end = data.get('end_date') or (self.instance.end_date if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError({'end_date': 'end_date must be after start_date.'})
        return data
