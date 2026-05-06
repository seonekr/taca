from rest_framework import serializers
from accounts.models import User
from .models import (
    Country, City,
    Restaurant, Category, Product, Order, OrderDetail,
    Payment, Review, ProductReview, DeliveryStatusLog, Notification,
    SearchHistory, PopularSearch, UserFavorite, AnalyticsDaily,
    RestaurantAnalytics, ProductAnalytics, AppSettings, Language, Translation,
    CategoryTranslation, ProductTranslation, GuestOrder, GuestOrderDetail, GuestDeliveryStatusLog,
    Advertisement, RestaurantTable, DineInCart, DineInCartItem, DineInOrder, 
    DineInOrderDetail, DineInStatusLog, DineInProduct, DineInProductTranslation,
    EntertainmentVenue, VenueImage, VenueCategory, VenueReview, VenueTranslation
)


def get_absolute_image_url(image_url, request=None):
    """Helper function to get absolute image URL"""
    if image_url and not image_url.startswith('http'):
        if request:
            return request.build_absolute_uri(image_url)
        else:
            # Fallback: use settings or environment variable
            from django.conf import settings
            base_url = getattr(settings, 'BASE_URL', None)
            if not base_url:
                import os
                base_url = os.environ.get('BASE_URL', 'https://matjyp.com')
            return f"{base_url}{image_url}"
    return image_url


# User serializer moved to accounts app


class CountrySerializer(serializers.ModelSerializer):
    flag_display_url = serializers.SerializerMethodField()

    class Meta:
        model = Country
        fields = [
            'country_id',
            'name',
            'flag',
            'flag_display_url',
            'sort_order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['country_id', 'flag', 'flag_display_url', 'created_at', 'updated_at']

    def get_flag_display_url(self, obj):
        if not obj.flag:
            return None
        return get_absolute_image_url(obj.flag.url, self.context.get('request'))


class CitySerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = City
        fields = ['city_id', 'country', 'country_name', 'name']
        read_only_fields = ['city_id']


class CategoryTranslationSerializer(serializers.ModelSerializer):
    language_code = serializers.CharField(source='language.code', read_only=True)
    language_name = serializers.CharField(source='language.name', read_only=True)
    
    class Meta:
        model = CategoryTranslation
        fields = ['language_code', 'language_name', 'translated_name', 'translated_description']


class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(source='products.count', read_only=True)
    image_display_url = serializers.SerializerMethodField()
    translations = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['category_id', 'category_name', 'description', 'image', 'image_display_url', 'is_special_only', 'sort_order', 'products_count', 'translations']
    
    def get_image_display_url(self, obj):
        """Get the category image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))
    
    def get_translations(self, obj):
        """
        Get translations, optionally filtered by language from query parameter
        à¸–à¹‰à¸²à¸¡à¸µ ?lang=th à¸ˆà¸°à¸ªà¹ˆà¸‡à¹à¸„à¹ˆ translation à¸ à¸²à¸©à¸²à¹„à¸—à¸¢
        à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¸¡à¸µ à¸ˆà¸°à¸ªà¹ˆà¸‡à¸—à¸¸à¸à¸ à¸²à¸©à¸² (backward compatible)
        """
        request = self.context.get('request')
        if request:
            lang_code = request.query_params.get('lang', None)
            if lang_code:
                # à¸ªà¹ˆà¸‡à¹à¸„à¹ˆà¸ à¸²à¸©à¸²à¸—à¸µà¹ˆà¸•à¹‰à¸­à¸‡à¸à¸²à¸£ (optimize performance)
                filtered_translations = obj.translations.filter(language__code=lang_code)
                return CategoryTranslationSerializer(filtered_translations, many=True).data
        
        # à¸ªà¹ˆà¸‡à¸—à¸¸à¸à¸ à¸²à¸©à¸² (default behavior - backward compatible)
        return CategoryTranslationSerializer(obj.translations.all(), many=True).data

    def create(self, validated_data):
        """Custom create method to handle translations"""
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)
        
        # Parse JSON string if needed (à¹€à¸¡à¸·à¹ˆà¸­à¸ªà¹ˆà¸‡à¸¡à¸²à¹€à¸›à¹‡à¸™ FormData)
        if isinstance(translations_data, str):
            import json
            try:
                translations_data = json.loads(translations_data)
                print(f"ðŸ“ Parsed category translations from JSON string: {translations_data}")
            except json.JSONDecodeError:
                print(f"âŒ Failed to parse category translations JSON: {translations_data}")
                translations_data = None
        
        # à¸ªà¸£à¹‰à¸²à¸‡à¸«à¸¡à¸§à¸”à¸«à¸¡à¸¹à¹ˆ
        category = Category.objects.create(**validated_data)
        print(f"âœ… Created category: {category.category_id} - {category.category_name}")
        
        # à¹€à¸žà¸´à¹ˆà¸¡à¸à¸²à¸£à¹à¸›à¸¥
        if translations_data:
            print(f"ðŸ“ Adding translations for category {category.category_id}")
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        CategoryTranslation.objects.create(
                            category=category,
                            language=language,
                            translated_name=translation_data['name'],
                            translated_description=translation_data.get('description', '')
                        )
                        print(f"âœ… Added {lang_code} translation: {translation_data['name']}")
                    except Language.DoesNotExist:
                        print(f"âŒ Language {lang_code} not found")
                        pass
        else:
            print(f"âš ï¸ No translations provided for category {category.category_id}")
        
        return category

    def update(self, instance, validated_data):
        """Custom update method to handle translations"""
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)
        
        # Parse JSON string if needed (à¹€à¸¡à¸·à¹ˆà¸­à¸ªà¹ˆà¸‡à¸¡à¸²à¹€à¸›à¹‡à¸™ FormData)
        if isinstance(translations_data, str):
            import json
            try:
                translations_data = json.loads(translations_data)
            except json.JSONDecodeError:
                translations_data = None
        
        # à¸­à¸±à¸›à¹€à¸”à¸•à¸«à¸¡à¸§à¸”à¸«à¸¡à¸¹à¹ˆ
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # à¸­à¸±à¸›à¹€à¸”à¸•à¸à¸²à¸£à¹à¸›à¸¥
        if translations_data:
            # à¸­à¸±à¸›à¹€à¸”à¸•à¸«à¸£à¸·à¸­à¹€à¸žà¸´à¹ˆà¸¡à¸à¸²à¸£à¹à¸›à¸¥à¸ªà¸³à¸«à¸£à¸±à¸šà¹à¸•à¹ˆà¸¥à¸°à¸ à¸²à¸©à¸²
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        translation, created = CategoryTranslation.objects.get_or_create(
                            category=instance,
                            language=language,
                            defaults={
                                'translated_name': translation_data['name'],
                                'translated_description': translation_data.get('description', '')
                            }
                        )
                        if not created:
                            # à¸­à¸±à¸›à¹€à¸”à¸•à¸à¸²à¸£à¹à¸›à¸¥à¸—à¸µà¹ˆà¸¡à¸µà¸­à¸¢à¸¹à¹ˆ
                            translation.translated_name = translation_data['name']
                            translation.translated_description = translation_data.get('description', '')
                            translation.save()
                    except Language.DoesNotExist:
                        pass
        
        return instance


class ProductTranslationSerializer(serializers.ModelSerializer):
    language_code = serializers.CharField(source='language.code', read_only=True)
    language_name = serializers.CharField(source='language.name', read_only=True)
    
    class Meta:
        model = ProductTranslation
        fields = ['language_code', 'language_name', 'translated_name', 'translated_description']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    restaurant_id = serializers.IntegerField(source='restaurant.restaurant_id', read_only=True)
    restaurant_status = serializers.CharField(source='restaurant.status', read_only=True)
    image_display_url = serializers.SerializerMethodField()
    translations = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = ['product_id', 'restaurant', 'restaurant_id', 'restaurant_name', 'restaurant_status', 'category', 
                 'category_name', 'product_name', 'description', 'price', 
                 'image_url', 'image', 'image_display_url', 'is_available', 'created_at', 'updated_at', 'translations']
        read_only_fields = ['product_id', 'created_at', 'updated_at']
    
    def get_image_display_url(self, obj):
        """Get the best available image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))
    
    def get_translations(self, obj):
        """
        Get translations, optionally filtered by language from query parameter
        à¸–à¹‰à¸²à¸¡à¸µ ?lang=th à¸ˆà¸°à¸ªà¹ˆà¸‡à¹à¸„à¹ˆ translation à¸ à¸²à¸©à¸²à¹„à¸—à¸¢
        à¸–à¹‰à¸²à¹„à¸¡à¹ˆà¸¡à¸µ à¸ˆà¸°à¸ªà¹ˆà¸‡à¸—à¸¸à¸à¸ à¸²à¸©à¸² (backward compatible)
        """
        request = self.context.get('request')
        if request:
            lang_code = request.query_params.get('lang', None)
            if lang_code:
                # à¸ªà¹ˆà¸‡à¹à¸„à¹ˆà¸ à¸²à¸©à¸²à¸—à¸µà¹ˆà¸•à¹‰à¸­à¸‡à¸à¸²à¸£ (optimize performance)
                filtered_translations = obj.translations.filter(language__code=lang_code)
                return ProductTranslationSerializer(filtered_translations, many=True).data
        
        # à¸ªà¹ˆà¸‡à¸—à¸¸à¸à¸ à¸²à¸©à¸² (default behavior - backward compatible)
        return ProductTranslationSerializer(obj.translations.all(), many=True).data
    
    def create(self, validated_data):
        """Custom create method to handle image upload and translations"""
        # Get translations data from request (for FormData) or validated_data (for JSON)
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)
        
        # Parse JSON string if needed (à¹€à¸¡à¸·à¹ˆà¸­à¸ªà¹ˆà¸‡à¸¡à¸²à¹€à¸›à¹‡à¸™ FormData)
        if isinstance(translations_data, str):
            import json
            try:
                translations_data = json.loads(translations_data)
                print(f"ðŸ“ Parsed translations from JSON string: {translations_data}")
            except json.JSONDecodeError:
                print(f"âŒ Failed to parse translations JSON: {translations_data}")
                translations_data = None
        
        # à¸ªà¸£à¹‰à¸²à¸‡à¸ªà¸´à¸™à¸„à¹‰à¸²
        product = Product.objects.create(**validated_data)
        print(f"âœ… Created product: {product.product_id} - {product.product_name}")
        
        # à¹€à¸žà¸´à¹ˆà¸¡à¸à¸²à¸£à¹à¸›à¸¥
        if translations_data:
            print(f"ðŸ“ Adding translations for product {product.product_id}")
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        ProductTranslation.objects.create(
                            product=product,
                            language=language,
                            translated_name=translation_data['name'],
                            translated_description=translation_data.get('description', '')
                        )
                        print(f"âœ… Added {lang_code} translation: {translation_data['name']}")
                    except Language.DoesNotExist:
                        print(f"âŒ Language {lang_code} not found")
                        pass
        else:
            print(f"âš ï¸ No translations provided for product {product.product_id}")
        
        return product

    def update(self, instance, validated_data):
        """Custom update method to handle translations"""
        # Get translations data from request (for FormData) or validated_data (for JSON)
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)
        
        # Parse JSON string if needed
        if isinstance(translations_data, str):
            import json
            translations_data = json.loads(translations_data)
        
        # Debug logs
        print(f"ðŸ”„ ProductSerializer.update - Product ID: {instance.product_id}")
        print(f"ðŸ“ translations_data: {translations_data}")
        
        # à¸­à¸±à¸›à¹€à¸”à¸•à¸ªà¸´à¸™à¸„à¹‰à¸²
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # à¸­à¸±à¸›à¹€à¸”à¸•à¸à¸²à¸£à¹à¸›à¸¥
        if translations_data is not None:
            print(f"ðŸ”„ Processing {len(translations_data)} translations")
            # à¸­à¸±à¸›à¹€à¸”à¸•à¸«à¸£à¸·à¸­à¹€à¸žà¸´à¹ˆà¸¡à¸à¸²à¸£à¹à¸›à¸¥à¸ªà¸³à¸«à¸£à¸±à¸šà¹à¸•à¹ˆà¸¥à¸°à¸ à¸²à¸©à¸²
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        print(f"ðŸ“ Creating/updating translation for {lang_code}: {translation_data['name']}")
                        translation, created = ProductTranslation.objects.get_or_create(
                            product=instance,
                            language=language,
                            defaults={
                                'translated_name': translation_data['name'],
                                'translated_description': translation_data.get('description', '')
                            }
                        )
                        if not created:
                            # à¸­à¸±à¸›à¹€à¸”à¸•à¸à¸²à¸£à¹à¸›à¸¥à¸—à¸µà¹ˆà¸¡à¸µà¸­à¸¢à¸¹à¹ˆ
                            print(f"ðŸ”„ Updating existing translation for {lang_code}")
                            translation.translated_name = translation_data['name']
                            translation.translated_description = translation_data.get('description', '')
                            translation.save()
                        else:
                            print(f"âœ… Created new translation for {lang_code}")
                    except Language.DoesNotExist:
                        print(f"âŒ Language {lang_code} does not exist")
                        pass
        else:
            print("âŒ No translations_data provided")
        
        return instance


class RestaurantSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    products_count = serializers.IntegerField(source='products.count', read_only=True)
    image_display_url = serializers.SerializerMethodField()
    country_name = serializers.CharField(source='country.name', read_only=True, allow_null=True)
    city_name = serializers.CharField(source='city.name', read_only=True, allow_null=True)
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(), allow_null=True, required=False,
    )
    city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), allow_null=True, required=False,
    )

    class Meta:
        model = Restaurant
        fields = ['restaurant_id', 'user', 'user_username', 'restaurant_name',
                 'description', 'address', 'country', 'country_name', 'city', 'city_name', 'latitude', 'longitude', 'phone_number', 'is_special',
                 'opening_hours', 'status', 'image', 'image_url', 'image_display_url', 'qr_code_image_url',
                 'bank_account_number', 'bank_name', 'account_name',
                 'average_rating', 'total_reviews', 'products_count',
                 'created_at', 'updated_at']
        read_only_fields = ['restaurant_id', 'average_rating', 'total_reviews',
                          'created_at', 'updated_at']

    def validate(self, attrs):
        country = attrs['country'] if 'country' in attrs else (self.instance.country if self.instance else None)
        city = attrs['city'] if 'city' in attrs else (self.instance.city if self.instance else None)
        if city and not country:
            raise serializers.ValidationError({'country': 'Select a country when a city is set.'})
        if city and country and city.country_id != country.country_id:
            raise serializers.ValidationError({'city': 'City does not belong to the selected country.'})
        return attrs
    
    def get_image_display_url(self, obj):
        """Get the best available image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))
    
    def validate_latitude(self, value):
        """Convert string to Decimal if needed and ensure max 12 decimal places"""
        if value is None or value == '':
            return None
        
        from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
        
        if isinstance(value, str):
            try:
                value = Decimal(value)
            except InvalidOperation:
                raise serializers.ValidationError('Invalid latitude value')
        
        if isinstance(value, float):
            value = Decimal(str(value))
        
        if value < -90 or value > 90:
            raise serializers.ValidationError('Latitude must be between -90 and 90')
        
        if isinstance(value, Decimal):
            return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        return value

    def validate_longitude(self, value):
        """Convert string to Decimal if needed and ensure max 12 decimal places"""
        if value is None or value == '':
            return None
        
        from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
        
        if isinstance(value, str):
            try:
                value = Decimal(value)
            except InvalidOperation:
                raise serializers.ValidationError('Invalid longitude value')
        
        if isinstance(value, float):
            value = Decimal(str(value))
        
        if value < -180 or value > 180:
            raise serializers.ValidationError('Longitude must be between -180 and 180')
        
        if isinstance(value, Decimal):
            return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        return value

    def update(self, instance, validated_data):
        """à¸­à¸±à¸›à¹€à¸”à¸—à¸£à¹‰à¸²à¸™à¹à¸¥à¸°à¸‹à¸´à¸‡à¸à¹Œ User role à¸­à¸±à¸•à¹‚à¸™à¸¡à¸±à¸•à¸´"""
        old_is_special = instance.is_special
        
        # à¸­à¸±à¸›à¹€à¸”à¸—à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¸£à¹‰à¸²à¸™
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # à¸‹à¸´à¸‡à¸à¹Œ User role à¹€à¸¡à¸·à¹ˆà¸­ is_special à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¹à¸›à¸¥à¸‡
        if 'is_special' in validated_data and validated_data['is_special'] != old_is_special:
            user = instance.user
            if user.role != 'admin':
                new_role = 'special_restaurant' if validated_data['is_special'] else 'general_restaurant'
                if user.role != new_role:
                    user.role = new_role
                    user.save()
                # print(f"ðŸ”„ Auto-sync: Restaurant {instance.restaurant_name} is_special={validated_data['is_special']} â†’ User {user.username} role={new_role}")
        
        return instance


class OrderDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_image_url = serializers.SerializerMethodField()
    image_display_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    restaurant_id = serializers.IntegerField(source='product.restaurant.restaurant_id', read_only=True)
    restaurant_name = serializers.CharField(source='product.restaurant.restaurant_name', read_only=True)
    
    class Meta:
        model = OrderDetail
        fields = ['order_detail_id', 'order', 'product', 'product_name', 'product_image_url',
                 'image_display_url', 'image_url', 'restaurant_id', 'restaurant_name', 
                 'quantity', 'price_at_order', 'subtotal']
        read_only_fields = ['order_detail_id', 'subtotal']
    
    def get_product_image_url(self, obj):
        """Get product image URL using the model's method"""
        image_url = obj.product.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))
    
    def get_image_display_url(self, obj):
        """Alias for compatibility"""
        return self.get_product_image_url(obj)
    
    def get_image_url(self, obj):
        """Alias for compatibility"""
        return self.get_product_image_url(obj)


class PaymentSerializer(serializers.ModelSerializer):
    proof_of_payment_display_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = ['payment_id', 'order', 'payment_date', 'amount_paid', 
                 'payment_method', 'transaction_id', 'status', 
                 'proof_of_payment_url', 'proof_of_payment', 'proof_of_payment_display_url']
        read_only_fields = ['payment_id', 'payment_date']
    
    def get_proof_of_payment_display_url(self, obj):
        """Get the best available proof of payment URL"""
        if obj.proof_of_payment:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.proof_of_payment.url)
            return obj.proof_of_payment.url
        return obj.proof_of_payment_url


class OrderSerializer(serializers.ModelSerializer):
    order_details = OrderDetailSerializer(many=True, read_only=True)
    order_details_by_restaurant = serializers.SerializerMethodField()
    payment = PaymentSerializer(read_only=True)
    customer_name = serializers.CharField(source='user.username', read_only=True)
    customer_phone = serializers.CharField(source='user.phone_number', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    restaurant_count = serializers.SerializerMethodField()
    is_multi_restaurant = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = ['order_id', 'user', 'customer_name', 'customer_phone', 'restaurant', 
                 'restaurant_name', 'order_date', 'total_amount', 
                 'delivery_address', 'delivery_latitude', 'delivery_longitude', 
                 'current_status', 'delivery_fee', 'estimated_delivery_time', 
                 'is_reviewed', 'order_details', 'order_details_by_restaurant',
                 'restaurant_count', 'is_multi_restaurant', 'payment']
        read_only_fields = ['order_id', 'order_date']
    
    def get_order_details_by_restaurant(self, obj):
        """à¸ˆà¸±à¸”à¸à¸¥à¸¸à¹ˆà¸¡ OrderDetail à¸•à¸²à¸¡à¸£à¹‰à¸²à¸™"""
        order_details = obj.order_details.all()
        restaurants = {}
        
        for detail in order_details:
            restaurant_id = detail.product.restaurant.restaurant_id
            restaurant_name = detail.product.restaurant.restaurant_name
            
            if restaurant_id not in restaurants:
                restaurants[restaurant_id] = {
                    'restaurant_id': restaurant_id,
                    'restaurant_name': restaurant_name,
                    'restaurant_address': detail.product.restaurant.address or '',
                    'items': [],
                    'subtotal': 0
                }
            
            item_data = OrderDetailSerializer(detail).data
            restaurants[restaurant_id]['items'].append(item_data)
            restaurants[restaurant_id]['subtotal'] += float(detail.subtotal)
        
        return list(restaurants.values())
    
    def get_restaurant_count(self, obj):
        """à¸™à¸±à¸šà¸ˆà¸³à¸™à¸§à¸™à¸£à¹‰à¸²à¸™à¹ƒà¸™à¸„à¸³à¸ªà¸±à¹ˆà¸‡à¸‹à¸·à¹‰à¸­"""
        return obj.order_details.values('product__restaurant').distinct().count()
    
    def get_is_multi_restaurant(self, obj):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸§à¹ˆà¸²à¹€à¸›à¹‡à¸™ multi-restaurant order à¸«à¸£à¸·à¸­à¹„à¸¡à¹ˆ"""
        return self.get_restaurant_count(obj) > 1


class CreateOrderSerializer(serializers.ModelSerializer):
    order_items = serializers.ListField(write_only=True)
    
    class Meta:
        model = Order
        fields = ['user', 'restaurant', 'delivery_address', 'delivery_latitude', 
                 'delivery_longitude', 'delivery_fee', 'order_items']
    
    def create(self, validated_data):
        order_items = validated_data.pop('order_items')
        
        # Calculate total amount
        total_amount = validated_data.get('delivery_fee', 0)
        for item in order_items:
            product = Product.objects.get(product_id=item['product_id'])
            total_amount += product.price * item['quantity']
        
        validated_data['total_amount'] = total_amount
        order = Order.objects.create(**validated_data)
        
        # Create order details
        for item in order_items:
            product = Product.objects.get(product_id=item['product_id'])
            OrderDetail.objects.create(
                order=order,
                product=product,
                quantity=item['quantity'],
                price_at_order=product.price
            )
        
        return order


class MultiRestaurantOrderSerializer(serializers.Serializer):
    """
    Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸à¸²à¸£à¸ªà¸±à¹ˆà¸‡à¸‹à¸·à¹‰à¸­à¸ˆà¸²à¸à¸«à¸¥à¸²à¸¢à¸£à¹‰à¸²à¸™à¹ƒà¸™à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§
    à¸£à¸°à¸šà¸šà¸ˆà¸°à¸ªà¸£à¹‰à¸²à¸‡ Order à¹€à¸”à¸µà¸¢à¸§à¸—à¸µà¹ˆà¸¡à¸µ OrderDetail à¸ˆà¸²à¸à¸«à¸¥à¸²à¸¢à¸£à¹‰à¸²à¸™
    """
    user = serializers.IntegerField()
    delivery_address = serializers.CharField(max_length=500)
    delivery_latitude = serializers.DecimalField(max_digits=20, decimal_places=12, required=False, allow_null=True)
    delivery_longitude = serializers.DecimalField(max_digits=20, decimal_places=12, required=False, allow_null=True)
    total_delivery_fee = serializers.DecimalField(max_digits=20, decimal_places=5)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    restaurants = serializers.JSONField(write_only=True)  # à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¹€à¸›à¹‡à¸™ JSONField à¹€à¸žà¸·à¹ˆà¸­à¸£à¸­à¸‡à¸£à¸±à¸š complex structure
    
    def validate_delivery_latitude(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¹à¸¥à¸°à¸›à¸£à¸±à¸šà¸„à¹ˆà¸² latitude"""
        if value is None:
            return value
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸‚à¸­à¸šà¹€à¸‚à¸• latitude (-90 à¸–à¸¶à¸‡ 90)
        if value < -90 or value > 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90")
        
        # à¸›à¸£à¸±à¸šà¹ƒà¸«à¹‰à¸¡à¸µà¸—à¸¨à¸™à¸´à¸¢à¸¡à¹„à¸¡à¹ˆà¹€à¸à¸´à¸™ 12 à¸«à¸¥à¸±à¸ (à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸«à¸¥à¸±à¸à¸£à¸§à¸¡)
        from decimal import Decimal, ROUND_HALF_UP
        return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
    
    def validate_delivery_longitude(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¹à¸¥à¸°à¸›à¸£à¸±à¸šà¸„à¹ˆà¸² longitude"""
        if value is None:
            return value
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸‚à¸­à¸šà¹€à¸‚à¸• longitude (-180 à¸–à¸¶à¸‡ 180)
        if value < -180 or value > 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180")
        
        # à¸›à¸£à¸±à¸šà¹ƒà¸«à¹‰à¸¡à¸µà¸—à¸¨à¸™à¸´à¸¢à¸¡à¹„à¸¡à¹ˆà¹€à¸à¸´à¸™ 12 à¸«à¸¥à¸±à¸ (à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸«à¸¥à¸±à¸à¸£à¸§à¸¡)
        from decimal import Decimal, ROUND_HALF_UP
        return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
    
    def validate_total_delivery_fee(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¹à¸¥à¸°à¸›à¸£à¸±à¸šà¸„à¹ˆà¸² delivery fee"""
        if value is None:
            return value
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸§à¹ˆà¸²à¹„à¸¡à¹ˆà¹€à¸›à¹‡à¸™à¸„à¹ˆà¸²à¸¥à¸š
        if value < 0:
            raise serializers.ValidationError("Delivery fee cannot be negative")
        
        # à¸›à¸£à¸±à¸šà¹ƒà¸«à¹‰à¸¡à¸µà¸—à¸¨à¸™à¸´à¸¢à¸¡à¹„à¸¡à¹ˆà¹€à¸à¸´à¸™ 5 à¸«à¸¥à¸±à¸ (à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸«à¸¥à¸±à¸)
        from decimal import Decimal, ROUND_HALF_UP
        return value.quantize(Decimal('0.00001'), rounding=ROUND_HALF_UP)
    
    def validate_restaurants(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¸£à¹‰à¸²à¸™à¹à¸¥à¸°à¸ªà¸´à¸™à¸„à¹‰à¸²"""
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("Must have at least 1 restaurant and must be a list")
        
        for i, restaurant_data in enumerate(value):
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š structure à¸‚à¸­à¸‡à¹à¸•à¹ˆà¸¥à¸°à¸£à¹‰à¸²à¸™
            if not isinstance(restaurant_data, dict):
                raise serializers.ValidationError(f"Restaurant data at index {i+1} must be an object")
            
            if 'restaurant_id' not in restaurant_data:
                raise serializers.ValidationError(f"Restaurant {i+1}: restaurant_id is required")
            if 'items' not in restaurant_data:
                raise serializers.ValidationError(f"Restaurant {i+1}: items list is required")
            
            restaurant_id = restaurant_data.get('restaurant_id')
            items = restaurant_data.get('items')
            
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š restaurant_id
            try:
                restaurant_id = int(restaurant_id)
                restaurant = Restaurant.objects.get(restaurant_id=restaurant_id)
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Restaurant {i+1}: restaurant_id must be a number")
            except Restaurant.DoesNotExist:
                raise serializers.ValidationError(f"Restaurant not found with ID: {restaurant_id}")
            
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š items
            if not isinstance(items, list) or not items:
                raise serializers.ValidationError(f"Restaurant {i+1}: must have at least 1 item in the list")
            
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸ªà¸´à¸™à¸„à¹‰à¸²à¹ƒà¸™à¸£à¹‰à¸²à¸™
            for j, item in enumerate(items):
                if not isinstance(item, dict):
                    raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: must be an object")
                
                if 'product_id' not in item or 'quantity' not in item:
                    raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: product_id and quantity are required")
                
                try:
                    product_id = int(item['product_id'])
                    quantity = int(item['quantity'])
                    
                    if quantity <= 0:
                        raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: quantity must be greater than 0")
                    
                    product = Product.objects.get(
                        product_id=product_id, 
                        restaurant=restaurant,
                        is_available=True
                    )
                except (ValueError, TypeError):
                    raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: product_id and quantity must be numbers")
                except Product.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Product not found with ID: {product_id} in restaurant {restaurant.restaurant_name}"
                    )
        
        return value
    
    def create(self, validated_data):
        restaurants_data = validated_data.pop('restaurants')
        
        # à¸ªà¸£à¹‰à¸²à¸‡ Order à¸«à¸¥à¸±à¸ (à¹„à¸¡à¹ˆà¸œà¸¹à¸à¸à¸±à¸šà¸£à¹‰à¸²à¸™à¹ƒà¸”à¸£à¹‰à¸²à¸™à¸«à¸™à¸¶à¹ˆà¸‡)
        # NOTE: à¸•à¹‰à¸­à¸‡à¹à¸à¹‰à¹„à¸‚ Model à¹€à¸žà¸·à¹ˆà¸­à¹ƒà¸«à¹‰ restaurant field à¹€à¸›à¹‡à¸™ optional
        
        # à¸§à¸´à¸˜à¸µà¹à¸à¹‰à¹„à¸‚à¸Šà¸±à¹ˆà¸§à¸„à¸£à¸²à¸§: à¹ƒà¸Šà¹‰à¸£à¹‰à¸²à¸™à¹à¸£à¸à¹€à¸›à¹‡à¸™ primary restaurant
        first_restaurant_id = restaurants_data[0]['restaurant_id']
        primary_restaurant = Restaurant.objects.get(restaurant_id=first_restaurant_id)
        
        # à¸„à¸³à¸™à¸§à¸“à¸¢à¸­à¸”à¸£à¸§à¸¡
        total_amount = validated_data.get('total_delivery_fee', 0)
        
        for restaurant_data in restaurants_data:
            restaurant = Restaurant.objects.get(restaurant_id=restaurant_data['restaurant_id'])
            for item_data in restaurant_data['items']:
                product = Product.objects.get(product_id=item_data['product_id'])
                total_amount += product.price * int(item_data['quantity'])
        
        # à¸ªà¸£à¹‰à¸²à¸‡ Order
        order = Order.objects.create(
            user_id=validated_data['user'],
            restaurant=primary_restaurant,  # à¸Šà¸±à¹ˆà¸§à¸„à¸£à¸²à¸§ à¹ƒà¸Šà¹‰à¸£à¹‰à¸²à¸™à¹à¸£à¸
            delivery_address=validated_data['delivery_address'],
            delivery_latitude=validated_data.get('delivery_latitude'),
            delivery_longitude=validated_data.get('delivery_longitude'),
            delivery_fee=validated_data['total_delivery_fee'],
            total_amount=total_amount,
            current_status='pending'
        )
        
        # à¸ªà¸£à¹‰à¸²à¸‡ OrderDetail à¸ªà¸³à¸«à¸£à¸±à¸šà¸—à¸¸à¸à¸ªà¸´à¸™à¸„à¹‰à¸²à¸ˆà¸²à¸à¸—à¸¸à¸à¸£à¹‰à¸²à¸™
        for restaurant_data in restaurants_data:
            restaurant = Restaurant.objects.get(restaurant_id=restaurant_data['restaurant_id'])
            for item_data in restaurant_data['items']:
                product = Product.objects.get(product_id=item_data['product_id'])
                OrderDetail.objects.create(
                    order=order,
                    product=product,
                    quantity=int(item_data['quantity']),
                    price_at_order=product.price
                )
        
        # à¸ªà¸£à¹‰à¸²à¸‡ status log
        DeliveryStatusLog.objects.create(
            order=order,
            status='pending',
            note=f'Multi-restaurant order created with {len(restaurants_data)} restaurants'
        )
        
        return order


class ReviewSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    
    class Meta:
        model = Review
        fields = ['review_id', 'user', 'user_username', 'order', 'restaurant', 
                 'restaurant_name', 'rating_restaurant', 'comment_restaurant', 
                 'review_date']
        read_only_fields = ['review_id', 'review_date', 'user']
    
    def validate_restaurant(self, value):
        """Validate that restaurant exists"""
        if not value:
            raise serializers.ValidationError("Restaurant is required")
        return value
    
    def validate_rating_restaurant(self, value):
        """Validate rating is between 1 and 5"""
        if not isinstance(value, int) or value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be an integer between 1 and 5")
        return value


class ProductReviewSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    
    class Meta:
        model = ProductReview
        fields = ['product_review_id', 'order_detail', 'user', 'user_username', 
                 'product', 'product_name', 'rating_product', 'comment_product', 
                 'review_date']
        read_only_fields = ['product_review_id', 'review_date']


class VenueReviewSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    venue_name = serializers.CharField(source='venue.venue_name', read_only=True)
    
    class Meta:
        model = VenueReview
        fields = ['review_id', 'venue', 'venue_name', 'user', 'user_username', 
                 'rating', 'comment', 'review_date', 'updated_at']
        read_only_fields = ['review_id', 'review_date', 'updated_at', 'user']
    
    def validate_venue(self, value):
        """Validate venue field - can be integer ID or EntertainmentVenue instance"""
        if value is None:
            raise serializers.ValidationError("Venue is required")
        # If it's an integer, try to get the venue
        if isinstance(value, (int, str)):
            try:
                from .models import EntertainmentVenue
                venue = EntertainmentVenue.objects.get(venue_id=int(value))
                return venue
            except EntertainmentVenue.DoesNotExist:
                raise serializers.ValidationError(f"Venue with ID {value} does not exist")
            except (ValueError, TypeError):
                raise serializers.ValidationError("Venue must be a valid integer ID")
        return value
    
    def validate_rating(self, value):
        """Validate rating is between 1 and 5"""
        if value is None:
            raise serializers.ValidationError("Rating is required")
        try:
            rating_int = int(value)
            if rating_int < 1 or rating_int > 5:
                raise serializers.ValidationError("Rating must be between 1 and 5")
            return rating_int
        except (ValueError, TypeError):
            raise serializers.ValidationError("Rating must be a valid integer")


class DeliveryStatusLogSerializer(serializers.ModelSerializer):
    updated_by_username = serializers.CharField(source='updated_by_user.username', read_only=True)
    
    class Meta:
        model = DeliveryStatusLog
        fields = ['log_id', 'order', 'status', 'timestamp', 'note', 
                 'updated_by_user', 'updated_by_username']
        read_only_fields = ['log_id', 'timestamp']


class NotificationSerializer(serializers.ModelSerializer):
    # à¹ƒà¸Šà¹‰ PrimaryKeyRelatedField à¸à¸±à¸š allow_null=True à¹€à¸žà¸·à¹ˆà¸­à¸›à¹‰à¸­à¸‡à¸à¸±à¸™ error à¹€à¸¡à¸·à¹ˆà¸­ related object à¸–à¸¹à¸à¸¥à¸š
    related_order = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)
    related_guest_order = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)
    
    class Meta:
        model = Notification
        fields = ['notification_id', 'user', 'title', 'message', 'type', 
                 'related_order', 'related_guest_order', 'is_read', 'created_at', 'read_at']
        read_only_fields = ['notification_id', 'created_at']


class SearchHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchHistory
        fields = ['search_id', 'user', 'search_query', 'search_type', 
                 'results_count', 'created_at']
        read_only_fields = ['search_id', 'created_at']


class PopularSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = PopularSearch
        fields = ['popular_search_id', 'search_query', 'search_count', 
                 'last_searched', 'updated_at']
        read_only_fields = ['popular_search_id', 'last_searched', 'updated_at']


class UserFavoriteSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    
    class Meta:
        model = UserFavorite
        fields = ['favorite_id', 'user', 'restaurant', 'restaurant_name', 
                 'product', 'product_name', 'favorite_type', 'created_at']
        read_only_fields = ['favorite_id', 'created_at']
    
    def validate(self, data):
        if data['favorite_type'] == 'restaurant' and not data.get('restaurant'):
            raise serializers.ValidationError("Restaurant is required for restaurant favorite")
        if data['favorite_type'] == 'product' and not data.get('product'):
            raise serializers.ValidationError("Product is required for product favorite")
        return data


class AnalyticsDailySerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsDaily
        fields = ['analytics_id', 'date', 'total_orders', 'total_revenue', 
                 'total_customers', 'new_customers', 'completed_orders', 
                 'cancelled_orders', 'average_order_value', 'created_at']
        read_only_fields = ['analytics_id', 'created_at']


class RestaurantAnalyticsSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    
    class Meta:
        model = RestaurantAnalytics
        fields = ['restaurant_analytics_id', 'restaurant', 'restaurant_name', 
                 'date', 'total_orders', 'total_revenue', 'completed_orders', 
                 'cancelled_orders', 'average_order_value', 'new_reviews', 
                 'created_at']
        read_only_fields = ['restaurant_analytics_id', 'created_at']


class ProductAnalyticsSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    
    class Meta:
        model = ProductAnalytics
        fields = ['product_analytics_id', 'product', 'product_name', 
                 'restaurant', 'restaurant_name', 'date', 'total_ordered', 
                 'total_quantity', 'total_revenue', 'created_at']
        read_only_fields = ['product_analytics_id', 'created_at']


# Authentication serializers moved to accounts app


class AppSettingsSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    qr_code_url = serializers.SerializerMethodField()
    
    class Meta:
        model = AppSettings
        fields = [
            'id', 'app_name', 'app_description', 'app_logo', 'app_banner',
            'logo_url', 'banner_url',
            'contact_email', 'contact_phone', 'contact_address',
            'hero_title', 'hero_subtitle',
            'feature_1_title', 'feature_1_description', 'feature_1_icon',
            'feature_2_title', 'feature_2_description', 'feature_2_icon',
            'feature_3_title', 'feature_3_description', 'feature_3_icon',
            'facebook_url', 'instagram_url', 'twitter_url',
            'meta_keywords', 'meta_description',
            'maintenance_mode', 'maintenance_message',
            'timezone', 'currency',
            'bank_name', 'bank_account_number', 'bank_account_name', 'qr_code_image', 'qr_code_url',
            'base_delivery_fee', 'free_delivery_minimum', 'max_delivery_distance', 'per_km_fee',
            'multi_restaurant_base_fee', 'multi_restaurant_additional_fee',
            'delivery_time_slots',
            'enable_scheduled_delivery', 'rush_hour_multiplier', 'weekend_multiplier',
            'created_at', 'updated_at', 'updated_by'
        ]
        read_only_fields = ['id', 'logo_url', 'banner_url', 'qr_code_url', 'created_at', 'updated_at', 'updated_by']
    
    def get_logo_url(self, obj):
        if obj.app_logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.app_logo.url)
            return obj.app_logo.url
        return None
    
    def get_banner_url(self, obj):
        if obj.app_banner:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.app_banner.url)
            return obj.app_banner.url
        return None
    
    def get_qr_code_url(self, obj):
        if obj.qr_code_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.qr_code_image.url)
            return obj.qr_code_image.url
        return None


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ['id', 'code', 'name', 'is_default', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class TranslationSerializer(serializers.ModelSerializer):
    language_code = serializers.CharField(source='language.code', read_only=True)
    
    class Meta:
        model = Translation
        fields = ['id', 'language', 'language_code', 'key', 'value', 'group', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at'] 

# Guest Order
class GuestOrderDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_image_url = serializers.SerializerMethodField()
    image_display_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    restaurant_id = serializers.IntegerField(source='restaurant.restaurant_id', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    translations = ProductTranslationSerializer(source='product.translations.all', many=True, read_only=True)

    class Meta:
        model = GuestOrderDetail
        fields = ['guest_order_detail_id', 'guest_order', 'product', 'product_name', 
                 'product_image_url', 'image_display_url', 'image_url', 'restaurant_id', 
                 'restaurant_name', 'quantity', 'price_at_order', 'subtotal', 'translations']
        read_only_fields = ['guest_order_detail_id', 'subtotal']
    
    def get_product_image_url(self, obj):
        """Get product image URL using the model's method"""
        image_url = obj.product.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))
    
    def get_image_display_url(self, obj):
        """Alias for compatibility"""
        return self.get_product_image_url(obj)
    
    def get_image_url(self, obj):
        """Alias for compatibility"""
        return self.get_product_image_url(obj)


class GuestOrderSerializer(serializers.ModelSerializer):
    order_details = GuestOrderDetailSerializer(many=True, read_only=True)
    order_details_by_restaurant = serializers.SerializerMethodField()
    restaurant_name = serializers.SerializerMethodField()
    status_logs = serializers.SerializerMethodField()
    restaurant_count = serializers.SerializerMethodField()
    is_multi_restaurant = serializers.SerializerMethodField()
    restaurants = serializers.SerializerMethodField()

    class Meta:
        model = GuestOrder
        fields = [
            'guest_order_id', 'temporary_id', 'restaurant', 'restaurants', 'restaurant_name',
            'order_date', 'total_amount', 'delivery_address', 'delivery_latitude',
            'delivery_longitude', 'current_status', 'delivery_fee',
            'estimated_delivery_time', 'customer_name', 'customer_phone',
            'customer_email', 'special_instructions', 'payment_method',
            'payment_status', 'proof_of_payment', 'expires_at', 'order_details',
            'order_details_by_restaurant', 'restaurant_count', 'is_multi_restaurant',
            'status_logs'
        ]
        read_only_fields = ['guest_order_id', 'temporary_id', 'order_date', 'expires_at']

    def get_restaurant_name(self, obj):
        """à¸”à¸¶à¸‡à¸Šà¸·à¹ˆà¸­à¸£à¹‰à¸²à¸™à¸«à¸¥à¸±à¸à¸«à¸£à¸·à¸­à¸Šà¸·à¹ˆà¸­à¸£à¹‰à¸²à¸™à¹à¸£à¸"""
        if obj.is_multi_restaurant:
            restaurant_names = obj.get_restaurant_names()
            return restaurant_names[0] if restaurant_names else 'Multi-Restaurant Order'
        elif obj.restaurant:
            return obj.restaurant.restaurant_name
        return 'Unknown Restaurant'

    def get_restaurants(self, obj):
        """à¸”à¸¶à¸‡à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¸£à¹‰à¸²à¸™à¸—à¸±à¹‰à¸‡à¸«à¸¡à¸”"""
        if obj.is_multi_restaurant:
            return obj.restaurants
        elif obj.restaurant:
            return [{
                'restaurant_id': obj.restaurant.restaurant_id,
                'restaurant_name': obj.restaurant.restaurant_name,
                'delivery_fee': float(obj.delivery_fee or 0)
            }]
        return []

    def get_status_logs(self, obj):
        logs = obj.status_logs.all().order_by('-timestamp')
        return [
            {
                'status': log.status,
                'timestamp': log.timestamp,
                'note': log.note,
                'updated_by': log.updated_by_user.username if log.updated_by_user else None
            }
            for log in logs
        ]

    def get_order_details_by_restaurant(self, obj):
        """à¸ˆà¸±à¸”à¸à¸¥à¸¸à¹ˆà¸¡ OrderDetail à¸•à¸²à¸¡à¸£à¹‰à¸²à¸™"""
        order_details = obj.order_details.all()
        restaurants = {}
        
        for detail in order_details:
            restaurant_id = detail.restaurant.restaurant_id
            restaurant_name = detail.restaurant.restaurant_name
            
            if restaurant_id not in restaurants:
                restaurants[restaurant_id] = {
                    'restaurant_id': restaurant_id,
                    'restaurant_name': restaurant_name,
                    'restaurant_address': detail.restaurant.address or '',
                    'items': [],
                    'subtotal': 0
                }
            
            item_data = GuestOrderDetailSerializer(detail).data
            restaurants[restaurant_id]['items'].append(item_data)
            restaurants[restaurant_id]['subtotal'] += float(detail.subtotal)
        
        return list(restaurants.values())
    
    def get_restaurant_count(self, obj):
        """à¸™à¸±à¸šà¸ˆà¸³à¸™à¸§à¸™à¸£à¹‰à¸²à¸™à¹ƒà¸™à¸„à¸³à¸ªà¸±à¹ˆà¸‡à¸‹à¸·à¹‰à¸­"""
        return obj.restaurant_count
    
    def get_is_multi_restaurant(self, obj):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸§à¹ˆà¸²à¹€à¸›à¹‡à¸™ multi-restaurant order à¸«à¸£à¸·à¸­à¹„à¸¡à¹ˆ"""
        return obj.is_multi_restaurant


class GuestMultiRestaurantOrderSerializer(serializers.Serializer):
    """
    Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸à¸²à¸£à¸ªà¸±à¹ˆà¸‡à¸‹à¸·à¹‰à¸­à¸ˆà¸²à¸à¸«à¸¥à¸²à¸¢à¸£à¹‰à¸²à¸™à¹ƒà¸™à¸„à¸£à¸±à¹‰à¸‡à¹€à¸”à¸µà¸¢à¸§ (Guest Order)
    à¸£à¸°à¸šà¸šà¸ˆà¸°à¸ªà¸£à¹‰à¸²à¸‡ GuestOrder à¹€à¸”à¸µà¸¢à¸§à¸—à¸µà¹ˆà¸¡à¸µ GuestOrderDetail à¸ˆà¸²à¸à¸«à¸¥à¸²à¸¢à¸£à¹‰à¸²à¸™
    """
    delivery_address = serializers.CharField(max_length=500)
    delivery_latitude = serializers.DecimalField(max_digits=20, decimal_places=12, required=False, allow_null=True)
    delivery_longitude = serializers.DecimalField(max_digits=20, decimal_places=12, required=False, allow_null=True)
    total_delivery_fee = serializers.DecimalField(max_digits=20, decimal_places=5)
    customer_name = serializers.CharField(max_length=100)
    customer_phone = serializers.CharField(max_length=20)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    special_instructions = serializers.CharField(max_length=500, required=False, allow_blank=True)
    payment_method = serializers.CharField(max_length=20, default='bank_transfer')
    restaurants = serializers.JSONField(write_only=True)
    
    def validate_delivery_latitude(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¹à¸¥à¸°à¸›à¸£à¸±à¸šà¸„à¹ˆà¸² latitude"""
        if value is None:
            return value
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸‚à¸­à¸šà¹€à¸‚à¸• latitude (-90 à¸–à¸¶à¸‡ 90)
        if value < -90 or value > 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90")
        
        # à¸›à¸£à¸±à¸šà¹ƒà¸«à¹‰à¸¡à¸µà¸—à¸¨à¸™à¸´à¸¢à¸¡à¹„à¸¡à¹ˆà¹€à¸à¸´à¸™ 12 à¸«à¸¥à¸±à¸ (à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸«à¸¥à¸±à¸à¸£à¸§à¸¡)
        from decimal import Decimal, ROUND_HALF_UP
        return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
    
    def validate_delivery_longitude(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¹à¸¥à¸°à¸›à¸£à¸±à¸šà¸„à¹ˆà¸² longitude"""
        if value is None:
            return value
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸‚à¸­à¸šà¹€à¸‚à¸• longitude (-180 à¸–à¸¶à¸‡ 180)
        if value < -180 or value > 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180")
        
        # à¸›à¸£à¸±à¸šà¹ƒà¸«à¹‰à¸¡à¸µà¸—à¸¨à¸™à¸´à¸¢à¸¡à¹„à¸¡à¹ˆà¹€à¸à¸´à¸™ 12 à¸«à¸¥à¸±à¸ (à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸«à¸¥à¸±à¸à¸£à¸§à¸¡)
        from decimal import Decimal, ROUND_HALF_UP
        return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
    
    def validate_total_delivery_fee(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¹à¸¥à¸°à¸›à¸£à¸±à¸šà¸„à¹ˆà¸² delivery fee"""
        if value is None:
            return value
        
        # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸§à¹ˆà¸²à¹„à¸¡à¹ˆà¹€à¸›à¹‡à¸™à¸„à¹ˆà¸²à¸¥à¸š
        if value < 0:
            raise serializers.ValidationError("Delivery fee cannot be negative")
        
        # à¸›à¸£à¸±à¸šà¹ƒà¸«à¹‰à¸¡à¸µà¸—à¸¨à¸™à¸´à¸¢à¸¡à¹„à¸¡à¹ˆà¹€à¸à¸´à¸™ 5 à¸«à¸¥à¸±à¸ (à¹„à¸¡à¹ˆà¸ˆà¸³à¸à¸±à¸”à¸ˆà¸³à¸™à¸§à¸™à¸«à¸¥à¸±à¸)
        from decimal import Decimal, ROUND_HALF_UP
        return value.quantize(Decimal('0.00001'), rounding=ROUND_HALF_UP)
    
    def validate_restaurants(self, value):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¸£à¹‰à¸²à¸™à¹à¸¥à¸°à¸ªà¸´à¸™à¸„à¹‰à¸²"""
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("Must have at least 1 restaurant and must be a list")
        
        for i, restaurant_data in enumerate(value):
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š structure à¸‚à¸­à¸‡à¹à¸•à¹ˆà¸¥à¸°à¸£à¹‰à¸²à¸™
            if not isinstance(restaurant_data, dict):
                raise serializers.ValidationError(f"Restaurant data at index {i+1} must be an object")
            
            if 'restaurant_id' not in restaurant_data:
                raise serializers.ValidationError(f"Restaurant {i+1}: restaurant_id is required")
            if 'items' not in restaurant_data:
                raise serializers.ValidationError(f"Restaurant {i+1}: items list is required")
            
            restaurant_id = restaurant_data.get('restaurant_id')
            items = restaurant_data.get('items')
            
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š restaurant_id
            try:
                restaurant_id = int(restaurant_id)
                restaurant = Restaurant.objects.get(restaurant_id=restaurant_id)
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Restaurant {i+1}: restaurant_id must be a number")
            except Restaurant.DoesNotExist:
                raise serializers.ValidationError(f"Restaurant not found with ID: {restaurant_id}")
            
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸š items
            if not isinstance(items, list) or not items:
                raise serializers.ValidationError(f"Restaurant {i+1}: must have at least 1 item in the list")
            
            # à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸ªà¸´à¸™à¸„à¹‰à¸²à¹ƒà¸™à¸£à¹‰à¸²à¸™
            for j, item in enumerate(items):
                if not isinstance(item, dict):
                    raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: must be an object")
                
                if 'product_id' not in item or 'quantity' not in item:
                    raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: product_id and quantity are required")
                
                try:
                    product_id = int(item['product_id'])
                    quantity = int(item['quantity'])
                    
                    if quantity <= 0:
                        raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: quantity must be greater than 0")
                    
                    product = Product.objects.get(
                        product_id=product_id, 
                        restaurant=restaurant,
                        is_available=True
                    )
                except (ValueError, TypeError):
                    raise serializers.ValidationError(f"Restaurant {i+1}, item {j+1}: product_id and quantity must be numbers")
                except Product.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Product not found with ID: {product_id} in restaurant {restaurant.restaurant_name}"
                    )
        
        return value
    
    def create(self, validated_data):
        restaurants_data = validated_data.pop('restaurants')
        
        # à¸„à¸³à¸™à¸§à¸“à¸¢à¸­à¸”à¸£à¸§à¸¡
        total_amount = validated_data.get('total_delivery_fee', 0)
        
        # à¹€à¸•à¸£à¸µà¸¢à¸¡à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¸£à¹‰à¸²à¸™à¸ªà¸³à¸«à¸£à¸±à¸š JSONField
        restaurants_json = []
        
        for restaurant_data in restaurants_data:
            restaurant = Restaurant.objects.get(restaurant_id=restaurant_data['restaurant_id'])
            restaurant_subtotal = 0
            
            for item_data in restaurant_data['items']:
                product = Product.objects.get(product_id=item_data['product_id'])
                restaurant_subtotal += product.price * int(item_data['quantity'])
            
            total_amount += restaurant_subtotal
            
            # à¹€à¸žà¸´à¹ˆà¸¡à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¸£à¹‰à¸²à¸™à¸¥à¸‡à¹ƒà¸™ JSON
            restaurants_json.append({
                'restaurant_id': restaurant.restaurant_id,
                'restaurant_name': restaurant.restaurant_name,
                'delivery_fee': float(restaurant_data.get('delivery_fee', 0))
            })
        
        # à¸ªà¸£à¹‰à¸²à¸‡ GuestOrder
        guest_order = GuestOrder.objects.create(
            restaurants=restaurants_json,  # à¹ƒà¸Šà¹‰ JSONField à¹ƒà¸«à¸¡à¹ˆ
            delivery_address=validated_data['delivery_address'],
            delivery_latitude=validated_data.get('delivery_latitude'),
            delivery_longitude=validated_data.get('delivery_longitude'),
            delivery_fee=validated_data['total_delivery_fee'],
            total_amount=total_amount,
            current_status='pending',
            customer_name=validated_data['customer_name'],
            customer_phone=validated_data['customer_phone'],
            customer_email=validated_data.get('customer_email', ''),
            special_instructions=validated_data.get('special_instructions', ''),
            payment_method=validated_data.get('payment_method', 'bank_transfer')
        )
        
        # à¸ªà¸£à¹‰à¸²à¸‡ GuestOrderDetail à¸ªà¸³à¸«à¸£à¸±à¸šà¸—à¸¸à¸à¸ªà¸´à¸™à¸„à¹‰à¸²à¸ˆà¸²à¸à¸—à¸¸à¸à¸£à¹‰à¸²à¸™
        for restaurant_data in restaurants_data:
            restaurant = Restaurant.objects.get(restaurant_id=restaurant_data['restaurant_id'])
            for item_data in restaurant_data['items']:
                product = Product.objects.get(product_id=item_data['product_id'])
                GuestOrderDetail.objects.create(
                    guest_order=guest_order,
                    product=product,
                    restaurant=restaurant,  # à¹€à¸žà¸´à¹ˆà¸¡ restaurant field
                    quantity=int(item_data['quantity']),
                    price_at_order=product.price
                )
        
        # à¸ªà¸£à¹‰à¸²à¸‡ status log
        GuestDeliveryStatusLog.objects.create(
            guest_order=guest_order,
            status='pending',
            note=f'Multi-restaurant guest order created with {len(restaurants_data)} restaurants'
        )
        
        return guest_order


class CreateGuestOrderSerializer(serializers.ModelSerializer):
    order_items = serializers.ListField(write_only=True)
    
    class Meta:
        model = GuestOrder
        fields = ['restaurant', 'delivery_address', 'delivery_latitude', 
                 'delivery_longitude', 'delivery_fee', 'customer_name', 
                 'customer_phone', 'customer_email', 'special_instructions', 
                 'payment_method', 'order_items', 'temporary_id']
        read_only_fields = ['temporary_id']
    
    def create(self, validated_data):
        order_items = validated_data.pop('order_items')
        
        # à¸„à¸³à¸™à¸§à¸“à¸¢à¸­à¸”à¸£à¸§à¸¡
        total_amount = validated_data.get('delivery_fee', 0)
        restaurant = validated_data.get('restaurant')
        
        for item in order_items:
            product = Product.objects.get(product_id=item['product_id'])
            total_amount += product.price * item['quantity']
        
        validated_data['total_amount'] = total_amount
        guest_order = GuestOrder.objects.create(**validated_data)
        
        # à¸ªà¸£à¹‰à¸²à¸‡à¸£à¸²à¸¢à¸¥à¸°à¹€à¸­à¸µà¸¢à¸”à¸„à¸³à¸ªà¸±à¹ˆà¸‡à¸‹à¸·à¹‰à¸­
        for item in order_items:
            product = Product.objects.get(product_id=item['product_id'])
            GuestOrderDetail.objects.create(
                guest_order=guest_order,
                product=product,
                restaurant=product.restaurant,  # à¹ƒà¸Šà¹‰ restaurant à¸ˆà¸²à¸ product
                quantity=item['quantity'],
                price_at_order=product.price
            )
        
        # à¸ªà¸£à¹‰à¸²à¸‡ status log à¹à¸£à¸
        GuestDeliveryStatusLog.objects.create(
            guest_order=guest_order,
            status='pending',
            note='Order created'
        )
        
        return guest_order


class GuestOrderTrackingSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    order_details = GuestOrderDetailSerializer(many=True, read_only=True)
    order_details_by_restaurant = serializers.SerializerMethodField()
    status_logs = serializers.SerializerMethodField()
    restaurant_count = serializers.SerializerMethodField()
    is_multi_restaurant = serializers.SerializerMethodField()

    class Meta:
        model = GuestOrder
        fields = [
            'guest_order_id', 'temporary_id', 'restaurant_name', 'order_date',
            'total_amount', 'delivery_address', 'current_status', 'delivery_fee',
            'estimated_delivery_time', 'customer_name', 'order_details',
            'order_details_by_restaurant', 'restaurant_count', 'is_multi_restaurant',
            'status_logs'
        ]

    def get_status_logs(self, obj):
        logs = obj.status_logs.all().order_by('-timestamp')
        return [
            {
                'status': log.status,
                'timestamp': log.timestamp,
                'note': log.note,
                'updated_by': log.updated_by_user.username if log.updated_by_user else None
            }
            for log in logs
        ]

    def get_order_details_by_restaurant(self, obj):
        """à¸ˆà¸±à¸”à¸à¸¥à¸¸à¹ˆà¸¡ OrderDetail à¸•à¸²à¸¡à¸£à¹‰à¸²à¸™"""
        order_details = obj.order_details.all()
        restaurants = {}
        
        for detail in order_details:
            restaurant_id = detail.product.restaurant.restaurant_id
            restaurant_name = detail.product.restaurant.restaurant_name
            
            if restaurant_id not in restaurants:
                restaurants[restaurant_id] = {
                    'restaurant_id': restaurant_id,
                    'restaurant_name': restaurant_name,
                    'restaurant_address': detail.product.restaurant.address or '',
                    'items': [],
                    'subtotal': 0
                }
            
            item_data = GuestOrderDetailSerializer(detail).data
            restaurants[restaurant_id]['items'].append(item_data)
            restaurants[restaurant_id]['subtotal'] += float(detail.subtotal)
        
        return list(restaurants.values())
    
    def get_restaurant_count(self, obj):
        """à¸™à¸±à¸šà¸ˆà¸³à¸™à¸§à¸™à¸£à¹‰à¸²à¸™à¹ƒà¸™à¸„à¸³à¸ªà¸±à¹ˆà¸‡à¸‹à¸·à¹‰à¸­"""
        return obj.order_details.values('product__restaurant').distinct().count()
    
    def get_is_multi_restaurant(self, obj):
        """à¸•à¸£à¸§à¸ˆà¸ªà¸­à¸šà¸§à¹ˆà¸²à¹€à¸›à¹‡à¸™ multi-restaurant order à¸«à¸£à¸·à¸­à¹„à¸¡à¹ˆ"""
        return self.get_restaurant_count(obj) > 1


class AdvertisementSerializer(serializers.ModelSerializer):
    image_display_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Advertisement
        fields = [
            'advertisement_id', 'image', 'image_display_url',
            'sort_order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['advertisement_id', 'created_at', 'updated_at']
    
    def get_image_display_url(self, obj):
        """Get the advertisement image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))


# ===== Dine-In QR Code System Serializers =====

class DineInProductTranslationSerializer(serializers.ModelSerializer):
    language_code = serializers.CharField(source='language.code', read_only=True)
    language_name = serializers.CharField(source='language.name', read_only=True)

    class Meta:
        model = DineInProductTranslation
        fields = ['language_code', 'language_name', 'translated_name', 'translated_description']


class DineInProductSerializer(serializers.ModelSerializer):
    """Serializer for restaurant-managed dine-in products."""
    image_display_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    translations = serializers.SerializerMethodField()

    class Meta:
        model = DineInProduct
        fields = [
            'dine_in_product_id', 'restaurant', 'restaurant_name', 'category', 'category_name',
            'product_name', 'description', 'price', 'image', 'image_url', 'image_display_url',
            'is_available', 'sort_order', 'is_recommended', 'preparation_time', 'translations',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['dine_in_product_id', 'restaurant', 'created_at', 'updated_at']

    def get_image_display_url(self, obj):
        """Get product image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))

    def get_translations(self, obj):
        request = self.context.get('request')
        if request:
            lang_code = request.query_params.get('lang', None)
            if lang_code:
                filtered_translations = obj.translations.filter(language__code=lang_code)
                return DineInProductTranslationSerializer(filtered_translations, many=True).data
        return DineInProductTranslationSerializer(obj.translations.all(), many=True).data

    def create(self, validated_data):
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)

        if isinstance(translations_data, str):
            import json
            try:
                translations_data = json.loads(translations_data)
            except json.JSONDecodeError:
                translations_data = None

        dine_in_product = DineInProduct.objects.create(**validated_data)

        if translations_data:
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        DineInProductTranslation.objects.create(
                            dine_in_product=dine_in_product,
                            language=language,
                            translated_name=translation_data['name'],
                            translated_description=translation_data.get('description', '')
                        )
                    except Language.DoesNotExist:
                        pass

        return dine_in_product

    def update(self, instance, validated_data):
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)

        if isinstance(translations_data, str):
            import json
            try:
                translations_data = json.loads(translations_data)
            except json.JSONDecodeError:
                translations_data = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if translations_data is not None:
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        translation, created = DineInProductTranslation.objects.get_or_create(
                            dine_in_product=instance,
                            language=language,
                            defaults={
                                'translated_name': translation_data['name'],
                                'translated_description': translation_data.get('description', '')
                            }
                        )
                        if not created:
                            translation.translated_name = translation_data['name']
                            translation.translated_description = translation_data.get('description', '')
                            translation.save()
                    except Language.DoesNotExist:
                        pass

        return instance


class RestaurantTableSerializer(serializers.ModelSerializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸ˆà¸±à¸”à¸à¸²à¸£à¹‚à¸•à¹Šà¸°à¸‚à¸­à¸‡à¸£à¹‰à¸²à¸™à¸­à¸²à¸«à¸²à¸£"""
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    qr_code_image_display_url = serializers.SerializerMethodField()
    qr_code_url = serializers.SerializerMethodField()
    
    class Meta:
        model = RestaurantTable
        fields = [
            'table_id', 'restaurant', 'restaurant_name', 'table_number',
            'qr_code_data', 'qr_code_image', 'qr_code_image_url',
            'qr_code_image_display_url', 'qr_code_url',
            'is_active', 'seats', 'created_at', 'updated_at'
        ]
        read_only_fields = ['table_id', 'restaurant', 'qr_code_data', 'created_at', 'updated_at']
    
    def get_qr_code_image_display_url(self, obj):
        """Get QR code image URL"""
        if obj.qr_code_image:
            return get_absolute_image_url(obj.qr_code_image.url, self.context.get('request'))
        elif obj.qr_code_image_url:
            return obj.qr_code_image_url
        return None
    
    def get_qr_code_url(self, obj):
        """à¸ªà¸£à¹‰à¸²à¸‡ URL à¸ªà¸³à¸«à¸£à¸±à¸šà¸¥à¸¹à¸à¸„à¹‰à¸²à¸ªà¹à¸à¸™ QR Code"""
        request = self.context.get('request')
        if request:
            from django.conf import settings
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            return f"{frontend_url}/dine-in/{obj.qr_code_data}"
        return None


class DineInCartItemSerializer(serializers.ModelSerializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸£à¸²à¸¢à¸à¸²à¸£à¹ƒà¸™à¸•à¸°à¸à¸£à¹‰à¸² Dine-in"""
    product_name = serializers.CharField(source='dine_in_product.product_name', read_only=True)
    product_image = serializers.SerializerMethodField()
    translations = DineInProductTranslationSerializer(source='dine_in_product.translations.all', many=True, read_only=True)
    restaurant_id = serializers.IntegerField(source='dine_in_product.restaurant.restaurant_id', read_only=True)
    restaurant_name = serializers.CharField(source='dine_in_product.restaurant.restaurant_name', read_only=True)
    
    class Meta:
        model = DineInCartItem
        fields = [
            'cart_item_id', 'cart', 'dine_in_product', 'product_name', 'product_image',
            'translations', 'restaurant_id', 'restaurant_name', 'quantity', 'price_at_add',
            'subtotal', 'special_instructions', 'created_at', 'updated_at'
        ]
        read_only_fields = ['cart_item_id', 'subtotal', 'created_at', 'updated_at']
    
    def get_product_image(self, obj):
        """Get product image URL"""
        image_url = obj.dine_in_product.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))


class DineInCartSerializer(serializers.ModelSerializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸•à¸°à¸à¸£à¹‰à¸² Dine-in"""
    items = DineInCartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True, source='get_total')
    table_number = serializers.CharField(source='table.table_number', read_only=True)
    restaurant_id = serializers.IntegerField(source='table.restaurant.restaurant_id', read_only=True)
    restaurant_name = serializers.CharField(source='table.restaurant.restaurant_name', read_only=True)
    item_count = serializers.SerializerMethodField()
    
    class Meta:
        model = DineInCart
        fields = [
            'cart_id', 'table', 'table_number', 'restaurant_id', 'restaurant_name',
            'session_id', 'customer_name', 'items', 'item_count', 'total',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['cart_id', 'created_at', 'updated_at']
    
    def get_item_count(self, obj):
        """à¸™à¸±à¸šà¸ˆà¸³à¸™à¸§à¸™à¸£à¸²à¸¢à¸à¸²à¸£à¹ƒà¸™à¸•à¸°à¸à¸£à¹‰à¸²"""
        return obj.items.count()


class AddToCartSerializer(serializers.Serializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¹€à¸žà¸´à¹ˆà¸¡à¸ªà¸´à¸™à¸„à¹‰à¸²à¸¥à¸‡à¸•à¸°à¸à¸£à¹‰à¸² Dine-in"""
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    special_instructions = serializers.CharField(required=False, allow_blank=True)


class UpdateCartItemSerializer(serializers.Serializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸­à¸±à¸›à¹€à¸”à¸•à¸£à¸²à¸¢à¸à¸²à¸£à¹ƒà¸™à¸•à¸°à¸à¸£à¹‰à¸²"""
    quantity = serializers.IntegerField(min_value=1)
    special_instructions = serializers.CharField(required=False, allow_blank=True)


class DineInOrderDetailSerializer(serializers.ModelSerializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸£à¸²à¸¢à¸¥à¸°à¹€à¸­à¸µà¸¢à¸”à¸­à¸­à¹€à¸”à¸­à¸£à¹Œ Dine-in"""
    product_name = serializers.CharField(source='dine_in_product.product_name', read_only=True)
    product_image = serializers.SerializerMethodField()
    translations = DineInProductTranslationSerializer(source='dine_in_product.translations.all', many=True, read_only=True)
    served_by_username = serializers.CharField(source='served_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = DineInOrderDetail
        fields = [
            'order_detail_id', 'order', 'dine_in_product', 'product_name', 'product_image',
            'translations', 'quantity', 'price_at_order', 'subtotal', 'special_instructions',
            'is_served', 'served_at', 'served_by', 'served_by_username'
        ]
        read_only_fields = ['order_detail_id', 'subtotal', 'served_at', 'served_by']
    
    def get_product_image(self, obj):
        """Get product image URL"""
        image_url = obj.dine_in_product.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))


class DineInStatusLogSerializer(serializers.ModelSerializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸š log à¸à¸²à¸£à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¸ªà¸–à¸²à¸™à¸°"""
    updated_by_username = serializers.CharField(source='updated_by_user.username', read_only=True)
    
    class Meta:
        model = DineInStatusLog
        fields = [
            'log_id', 'order', 'status', 'timestamp', 'note',
            'updated_by_user', 'updated_by_username'
        ]
        read_only_fields = ['log_id', 'timestamp']


class DineInOrderSerializer(serializers.ModelSerializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸­à¸­à¹€à¸”à¸­à¸£à¹Œ Dine-in"""
    order_details = DineInOrderDetailSerializer(many=True, read_only=True)
    status_logs = DineInStatusLogSerializer(many=True, read_only=True)
    table_number = serializers.CharField(source='table.table_number', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.restaurant_name', read_only=True)
    
    class Meta:
        model = DineInOrder
        fields = [
            'dine_in_order_id', 'table', 'table_number', 'restaurant', 'restaurant_name',
            'session_id', 'order_date', 'total_amount', 'current_status', 'payment_status',
            'customer_name', 'customer_count', 'special_instructions',
            'payment_method', 'paid_at', 'completed_at',
            'bill_requested', 'bill_requested_at',
            'order_details', 'status_logs'
        ]
        read_only_fields = ['dine_in_order_id', 'order_date', 'paid_at', 'completed_at', 'bill_requested_at']


class CreateDineInOrderSerializer(serializers.Serializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸ªà¸£à¹‰à¸²à¸‡à¸­à¸­à¹€à¸”à¸­à¸£à¹Œ Dine-in à¸ˆà¸²à¸à¸•à¸°à¸à¸£à¹‰à¸²"""
    customer_name = serializers.CharField(required=False, allow_blank=True)
    customer_count = serializers.IntegerField(min_value=1, default=1)
    special_instructions = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.CharField(required=False, default='cash')


class UpdateDineInOrderStatusSerializer(serializers.Serializer):
    """Serializer à¸ªà¸³à¸«à¸£à¸±à¸šà¸­à¸±à¸›à¹€à¸”à¸•à¸ªà¸–à¸²à¸™à¸°à¸­à¸­à¹€à¸”à¸­à¸£à¹Œ"""
    status = serializers.ChoiceField(choices=DineInOrder.STATUS_CHOICES)
    note = serializers.CharField(required=False, allow_blank=True)


# ===== Entertainment Venues Serializers =====

class VenueImageSerializer(serializers.ModelSerializer):
    """Serializer for venue images"""
    image_display_url = serializers.SerializerMethodField()
    
    class Meta:
        model = VenueImage
        fields = ['image_id', 'venue', 'image', 'image_url', 'image_display_url', 'caption', 'sort_order', 'is_primary', 'created_at', 'updated_at']
        read_only_fields = ['image_id', 'created_at', 'updated_at']
    
    def get_image_display_url(self, obj):
        """Get the image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))


class VenueCategorySerializer(serializers.ModelSerializer):
    """Serializer for venue categories"""
    icon_display_url = serializers.SerializerMethodField()
    venues_count = serializers.IntegerField(source='venues.count', read_only=True)
    
    class Meta:
        model = VenueCategory
        fields = ['category_id', 'category_name', 'description', 'icon', 'icon_url', 'icon_display_url', 'sort_order', 'is_active', 'venues_count', 'created_at', 'updated_at']
        read_only_fields = ['category_id', 'created_at', 'updated_at']
    
    def get_icon_display_url(self, obj):
        """Get the category icon URL"""
        icon_url = obj.get_icon_url()
        return get_absolute_image_url(icon_url, self.context.get('request'))


class VenueTranslationSerializer(serializers.ModelSerializer):
    language_code = serializers.CharField(source='language.code', read_only=True)
    language_name = serializers.CharField(source='language.name', read_only=True)

    class Meta:
        model = VenueTranslation
        fields = ['language_code', 'language_name', 'translated_name', 'translated_description']


class EntertainmentVenueSerializer(serializers.ModelSerializer):
    """Serializer for entertainment venues"""
    image_display_url = serializers.SerializerMethodField()
    images = VenueImageSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True, allow_null=True)
    city_name = serializers.CharField(source='city.name', read_only=True, allow_null=True)
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(), allow_null=True, required=False,
    )
    city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), allow_null=True, required=False,
    )
    translations = serializers.SerializerMethodField()

    class Meta:
        model = EntertainmentVenue
        fields = [
            'venue_id', 'venue_name', 'description', 'address', 'country', 'country_name', 'city', 'city_name', 'latitude', 'longitude',
            'phone_number', 'opening_hours', 'status', 'category', 'category_name',
            'image', 'image_url', 'image_display_url', 'average_rating', 'total_reviews',
            'images', 'created_at', 'updated_at', 'translations'
        ]
        read_only_fields = ['venue_id', 'average_rating', 'total_reviews', 'created_at', 'updated_at']

    def get_translations(self, obj):
        request = self.context.get('request')
        if request:
            lang_code = request.query_params.get('lang', None)
            if lang_code:
                filtered = obj.translations.filter(language__code=lang_code)
                return VenueTranslationSerializer(filtered, many=True).data
        return VenueTranslationSerializer(obj.translations.all(), many=True).data

    def create(self, validated_data):
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)
        if isinstance(translations_data, str):
            import json
            try:
                translations_data = json.loads(translations_data)
            except json.JSONDecodeError:
                translations_data = None

        venue = EntertainmentVenue.objects.create(**validated_data)

        if translations_data:
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        VenueTranslation.objects.create(
                            venue=venue,
                            language=language,
                            translated_name=translation_data['name'],
                            translated_description=translation_data.get('description', '')
                        )
                    except Language.DoesNotExist:
                        pass

        return venue

    def update(self, instance, validated_data):
        translations_data = self.context.get('request').data.get('translations') if self.context.get('request') else validated_data.pop('translations', None)
        if isinstance(translations_data, str):
            import json
            try:
                translations_data = json.loads(translations_data)
            except json.JSONDecodeError:
                translations_data = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if translations_data is not None:
            for lang_code, translation_data in translations_data.items():
                if translation_data.get('name'):
                    try:
                        language = Language.objects.get(code=lang_code)
                        translation, created = VenueTranslation.objects.get_or_create(
                            venue=instance,
                            language=language,
                            defaults={
                                'translated_name': translation_data['name'],
                                'translated_description': translation_data.get('description', '')
                            }
                        )
                        if not created:
                            translation.translated_name = translation_data['name']
                            translation.translated_description = translation_data.get('description', '')
                            translation.save()
                    except Language.DoesNotExist:
                        pass

        return instance

    def validate(self, attrs):
        country = attrs['country'] if 'country' in attrs else (self.instance.country if self.instance else None)
        city = attrs['city'] if 'city' in attrs else (self.instance.city if self.instance else None)
        if city and not country:
            raise serializers.ValidationError({'country': 'Select a country when a city is set.'})
        if city and country and city.country_id != country.country_id:
            raise serializers.ValidationError({'city': 'City does not belong to the selected country.'})
        return attrs
    
    def validate_latitude(self, value):
        """Convert string to Decimal if needed and ensure max 12 decimal places"""
        if value is None or value == '':
            return None
        if isinstance(value, str):
            try:
                from decimal import Decimal, ROUND_HALF_UP
                decimal_value = Decimal(value)
                # Round to 12 decimal places
                return decimal_value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
            except (ValueError, TypeError):
                return None
        if isinstance(value, (int, float)):
            from decimal import Decimal, ROUND_HALF_UP
            decimal_value = Decimal(str(value))
            return decimal_value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        # If already Decimal, round it
        if hasattr(value, 'quantize'):
            from decimal import Decimal, ROUND_HALF_UP
            return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        return value
    
    def validate_longitude(self, value):
        """Convert string to Decimal if needed and ensure max 12 decimal places"""
        if value is None or value == '':
            return None
        if isinstance(value, str):
            try:
                from decimal import Decimal, ROUND_HALF_UP
                decimal_value = Decimal(value)
                # Round to 12 decimal places
                return decimal_value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
            except (ValueError, TypeError):
                return None
        if isinstance(value, (int, float)):
            from decimal import Decimal, ROUND_HALF_UP
            decimal_value = Decimal(str(value))
            return decimal_value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        # If already Decimal, round it
        if hasattr(value, 'quantize'):
            from decimal import Decimal, ROUND_HALF_UP
            return value.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP)
        return value
    
    def validate_category(self, value):
        """Handle category field - can be None, ID, or empty string"""
        if value is None or value == '':
            return None
        return value
    
    def get_image_display_url(self, obj):
        """Get the venue image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))


class EntertainmentVenueListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for venue list (without images)"""
    image_display_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True, allow_null=True)
    city_name = serializers.CharField(source='city.name', read_only=True, allow_null=True)
    translations = serializers.SerializerMethodField()

    class Meta:
        model = EntertainmentVenue
        fields = [
            'venue_id', 'venue_name', 'description', 'address', 'country', 'country_name', 'city', 'city_name', 'latitude', 'longitude',
            'phone_number', 'opening_hours', 'status', 'category', 'category_name',
            'image_display_url', 'average_rating', 'total_reviews', 'created_at', 'translations'
        ]
        read_only_fields = ['venue_id', 'average_rating', 'total_reviews', 'created_at']

    def get_translations(self, obj):
        request = self.context.get('request')
        if request:
            lang_code = request.query_params.get('lang', None)
            if lang_code:
                filtered = obj.translations.filter(language__code=lang_code)
                return VenueTranslationSerializer(filtered, many=True).data
        return VenueTranslationSerializer(obj.translations.all(), many=True).data
    
    def get_image_display_url(self, obj):
        """Get the venue image URL"""
        image_url = obj.get_image_url()
        return get_absolute_image_url(image_url, self.context.get('request'))

