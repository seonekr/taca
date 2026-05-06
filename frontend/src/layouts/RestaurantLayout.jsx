import React, { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import Header from "../components/common/Header";
import { useRestaurantNotification } from "../contexts/RestaurantNotificationContext";
import { useLanguage } from "../contexts/LanguageContext";
import NotificationPanel from "../components/restaurant/NotificationPanel";
import { FaChartBar, FaBox, FaUtensils, FaClipboardList, FaStar, FaChartLine, FaStore } from 'react-icons/fa';

const RestaurantLayout = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { newOrdersCount, notifications, removeNotification } = useRestaurantNotification();
  const { translate } = useLanguage();
  const [notificationPanelVisible, setNotificationPanelVisible] = useState(false);
  const prevNotificationsLengthRef = useRef(0);

  useEffect(() => {
    const prevLength = prevNotificationsLengthRef.current;
    const currentLength = notifications.length;

    if (currentLength > prevLength && currentLength > 0) {
      setNotificationPanelVisible(true);
    }

    prevNotificationsLengthRef.current = currentLength;
  }, [notifications.length]);

  return (
    <div className="min-h-screen bg-secondary-50">
      <Header />

      <NotificationPanel
        notifications={notifications}
        onClose={() => setNotificationPanelVisible(false)}
        onRemove={removeNotification}
        isVisible={notificationPanelVisible}
      />

      <div className="flex pt-16">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="lg:hidden fixed top-20 left-4 z-30 p-2 rounded-md bg-white shadow-lg text-secondary-600 hover:text-secondary-900 hover:bg-secondary-50"
        >
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        {sidebarOpen && (
          <div
            className="lg:hidden fixed inset-0 z-10 bg-black bg-opacity-50"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <aside
          className={`fixed left-0 top-16 w-64 h-screen bg-white shadow-lg z-20 overflow-y-auto transition-transform duration-300 ease-in-out lg:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <nav className="p-4">
            <div className="space-y-2">
              <Link
                to="/restaurant"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
              >
                <FaChartBar className="w-5 h-5 mr-2" /> {translate('restaurant.dashboard') || 'Dashboard'}
              </Link>

              <Link
                to="/restaurant/orders"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center justify-between px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
              >
                <span className="flex items-center">
                  <FaBox className="w-5 h-5 mr-2" /> {translate('restaurant.orders') || 'Orders'}
                </span>
                {newOrdersCount > 0 && (
                  <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-white bg-red-600 rounded-full">
                    {newOrdersCount}
                  </span>
                )}
              </Link>

              <div className="pt-2 pb-1 px-4">
                <p className="text-xs font-semibold text-secondary-400 uppercase">
                  {translate('restaurant.dine_in_system') || 'Dine-in System'}
                </p>
              </div>

              <Link
                to="/restaurant/dine-in-products"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
              >
                <FaUtensils className="w-5 h-5 mr-2" /> {translate('restaurant.dine_in_products_menu') || 'Dine-in Products'}
              </Link>

              <Link
                to="/restaurant/tables"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
              >
                <FaClipboardList className="w-5 h-5 mr-2" /> {translate('restaurant.tables_qr_management') || 'Tables & QR Code'}
              </Link>

              <div className="pt-2 pb-1 px-4">
                <p className="text-xs font-semibold text-secondary-400 uppercase">{translate('common.others') || 'Other'}</p>
              </div>

              <Link
                to="/restaurant/reviews"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
              >
                <FaStar className="w-5 h-5 mr-2" /> {translate('restaurant.reviews') || 'Reviews'}
              </Link>

              <Link
                to="/restaurant/analytics"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
              >
                <FaChartLine className="w-5 h-5 mr-2" /> {translate('restaurant.analytics') || 'Analytics'}
              </Link>

              <Link
                to="/restaurant/profile"
                onClick={() => setSidebarOpen(false)}
                className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
              >
                <FaStore className="w-5 h-5 mr-2" /> {translate('restaurant.information') || 'Store Information'}
              </Link>
            </div>
          </nav>
        </aside>

        <main className="flex-1 lg:ml-64 min-h-screen">
          <div className="p-4 lg:p-8">{children}</div>
        </main>
      </div>
    </div>
  );
};

export default RestaurantLayout;
