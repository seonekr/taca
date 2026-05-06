import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { FaClipboardList, FaDollarSign, FaUtensils, FaStar, FaRocket, FaSpinner } from 'react-icons/fa';
import { dashboardService } from '../../services/api';
import api from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { useLanguage } from '../../contexts/LanguageContext';

const RestaurantDashboard = () => {
  const { user } = useAuth();
  const { translate } = useLanguage();
  const [loading, setLoading] = useState(true);
  const [noStore, setNoStore] = useState(false);
  const [stats, setStats] = useState({
    todayOrders: 0,
    todaySales: 0,
    totalMenu: 0,
    averageRating: 0.0
  });

  const t = (key, fallback, vars = {}) => {
    const value = translate(key, vars);
    return value === key ? fallback : value;
  };

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        
        // ดึงข้อมูล dashboard
        const dashboardResponse = await dashboardService.getRestaurant();
        const dashboardData = dashboardResponse.data;
        
        // ดึงจำนวนเมนูทั้งหมด (dine-in products)
        let totalMenuCount = 0;
        try {
          // หา restaurant ID
          const restaurantId = user?.restaurant_info?.id || user?.restaurant?.restaurant_id || user?.restaurant_id;
          
          if (restaurantId) {
            const productsResponse = await api.get('/dine-in-products/', {
              params: { restaurant: restaurantId }
            });
            const products = Array.isArray(productsResponse.data) 
              ? productsResponse.data 
              : productsResponse.data?.results || [];
            totalMenuCount = products.length;
          }
        } catch (error) {
          console.error('Error fetching products:', error);
        }
        
        const todayOrders = dashboardData.today?.orders || 0;
        const todaySales = parseFloat(dashboardData.today?.revenue || 0);
        
        setStats({
          todayOrders: todayOrders,
          todaySales: todaySales,
          totalMenu: totalMenuCount,
          averageRating: parseFloat(dashboardData.restaurant?.average_rating || 0)
        });
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
        if (error?.response?.status === 404) setNoStore(true);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, [user]);

  const formatPrice = (price) => {
    return new Intl.NumberFormat('th-TH', {
      style: 'currency',
      currency: 'THB',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(price);
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <FaSpinner className="animate-spin text-4xl text-primary-600" />
        </div>
      </div>
    );
  }

  if (noStore) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow-md p-8 text-center">
          <div className="text-6xl mb-4 opacity-30">🏪</div>
          <h2 className="text-xl font-semibold text-secondary-700 mb-2">
            {t('restaurant.no_store_linked', 'No store linked to this account')}
          </h2>
          <p className="text-secondary-500 mb-6">
            {t('restaurant.no_store_linked_desc', 'Please link a store to your account in the admin panel first.')}
          </p>
          <Link to="/admin/restaurants" className="bg-primary-500 text-white px-6 py-3 rounded-lg hover:bg-primary-600 transition-colors">
            {t('restaurant.go_to_stores', 'Go to Stores Management')}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-secondary-800 mb-6">
        {t('restaurant.dashboard.title', 'Store dashboard')}
      </h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center">
            <div className="text-3xl text-blue-500 mr-4">
              <FaClipboardList className="w-8 h-8" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-secondary-700">
                {t('restaurant.dashboard.today_orders', "Today's order")}
              </h3>
              <p className="text-2xl font-bold text-secondary-800">{stats.todayOrders}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center">
            <div className="text-3xl text-green-500 mr-4">
              <FaDollarSign className="w-8 h-8" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-secondary-700">
                {t('restaurant.dashboard.today_sales', "Today's sales")}
              </h3>
              <p className="text-2xl font-bold text-secondary-800">{formatPrice(stats.todaySales)}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center">
            <div className="text-3xl text-yellow-500 mr-4">
              <FaUtensils className="w-8 h-8" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-secondary-700">
                {t('restaurant.dashboard.total_menu', 'Total menu')}
              </h3>
              <p className="text-2xl font-bold text-secondary-800">{stats.totalMenu}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center">
            <div className="text-3xl text-orange-500 mr-4">
              <FaStar className="w-8 h-8" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-secondary-700">
                {t('restaurant.dashboard.average_rating', 'Average rating')}
              </h3>
              <p className="text-2xl font-bold text-secondary-800">{stats.averageRating.toFixed(1)}</p>
            </div>
          </div>
        </div>
      </div>
      <div className="bg-white rounded-lg shadow-md p-8 text-center">
        <div className="flex justify-center mb-4 opacity-30">
          <FaRocket className="w-16 h-16 text-primary-500" />
        </div>
        <h2 className="text-xl font-semibold text-secondary-700 mb-2">
          {t('restaurant.dashboard.cta_title', 'Start managing your store')}
        </h2>
        <p className="text-secondary-500 mb-6">
          {t('restaurant.dashboard.cta_subtitle', 'Add menu, manage orders, and track sales')}
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link to="/restaurant/dine-in-products" className="bg-primary-500 text-white px-6 py-3 rounded-lg hover:bg-primary-600 transition-colors">
            {t('restaurant.dashboard.manage_menu', 'Manage menu')}
          </Link>
          <Link to="/restaurant/orders" className="bg-secondary-200 text-secondary-700 px-6 py-3 rounded-lg hover:bg-secondary-300 transition-colors">
            {t('restaurant.dashboard.view_orders', 'View orders')}
          </Link>
        </div>
      </div>
    </div>
  );
};

export default RestaurantDashboard;
