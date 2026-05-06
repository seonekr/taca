import React, {
  useState,
  useEffect,
  createContext,
  useContext,
  useCallback,
} from "react";
import { Link } from "react-router-dom";
import Header from "../components/common/Header";
import { notificationService } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import websocketService from "../services/websocket";
import AdminNotificationBridge from "../components/admin/AdminNotificationBridge";
import { useLocation } from "react-router-dom";
import { FaBars, FaTimes, FaChartBar, FaUsers, FaStore, FaFolder, FaCog, FaBullhorn, FaUtensils } from "react-icons/fa";
import { FaUserCheck, FaUserXmark } from "react-icons/fa6";
import { IoIosCreate  } from "react-icons/io";
import { BiSolidPhoneCall } from "react-icons/bi";
import { useLanguage } from "../contexts/LanguageContext";

// Create context for notification count
const NotificationContext = createContext();

export const useNotificationContext = () => {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error(
      "useNotificationContext must be used within NotificationProvider"
    );
  }
  return context;
};

const AdminLayout = ({ children }) => {
  const { translate } = useLanguage();
  const { user, token } = useAuth();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  
  // Badge counts for specific order types
  const [ordersBadgeCount, setOrdersBadgeCount] = useState(0);
  const [guestOrdersBadgeCount, setGuestOrdersBadgeCount] = useState(0);
  
  // ตรวจสอบว่าอยู่ในหน้า Phone Orders หรือไม่
  const isPhoneOrdersPage = location.pathname.includes('/phone-order');

  // Debug logging for unreadCount changes
  useEffect(() => {
    console.log("📊 UnreadCount state changed to:", unreadCount);
  }, [unreadCount]);

  // Debug logging for badge counts
  useEffect(() => {
    console.log("🏷️ Orders badge count changed to:", ordersBadgeCount);
  }, [ordersBadgeCount]);

  useEffect(() => {
    console.log("🏷️ Guest orders badge count changed to:", guestOrdersBadgeCount);
  }, [guestOrdersBadgeCount]);

  // Fetch unread notifications count function
  const fetchUnreadCount = useCallback(async () => {
    try {
      const response = await notificationService.getUnreadCount();
      const count = response.data.unread_count || 0;
      setUnreadCount(count);
    } catch (error) {
      try {
        const notifResponse = await notificationService.getAll({
          is_read: "false",
        });
        const unreadNotifs = (
          notifResponse.data.results || notifResponse.data
        ).filter((n) => !n.is_read);
        setUnreadCount(unreadNotifs.length);
      } catch (fallbackError) {
        console.error("❌ Fallback count also failed:", fallbackError);
      }
    }
  }, []);

  // Fetch badge counts from database
  const fetchBadgeCounts = useCallback(async () => {
    try {
      console.log("🔍 Fetching badge counts from database...");
      const response = await notificationService.getBadgeCounts();
      
      const regularOrdersCount = response.data.regular_orders_count || 0;
      const guestOrdersCount = response.data.guest_orders_count || 0;
      
      setOrdersBadgeCount(regularOrdersCount);
      setGuestOrdersBadgeCount(guestOrdersCount);
      
      console.log("✅ Badge counts fetched from database - Orders:", regularOrdersCount, "Guest Orders:", guestOrdersCount);
      
    } catch (error) {
      console.error("❌ Error fetching badge counts:", error);
      
      // Fallback: ถ้า API endpoint ใหม่ไม่ทำงาน ให้ลองใช้วิธีเดิม
      try {
        console.log("⚠️ Falling back to old method...");
        const response = await notificationService.getAll({
          is_read: "false",
          limit: 200,
        });
        const unreadNotifs = (response.data.results || response.data).filter((n) => !n.is_read);
        
        // Count notifications by type
        let regularOrdersCount = 0;
        let guestOrdersCount = 0;
        
        unreadNotifs.forEach(notif => {
          if (notif.type === 'guest_order' && notif.related_guest_order) {
            guestOrdersCount++;
          } else if (notif.type === 'order' && notif.related_order) {
            regularOrdersCount++;
          }
        });
        
        setOrdersBadgeCount(regularOrdersCount);
        setGuestOrdersBadgeCount(guestOrdersCount);
        
        console.log("✅ Badge counts fetched using fallback - Orders:", regularOrdersCount, "Guest Orders:", guestOrdersCount);
      } catch (fallbackError) {
        console.error("❌ Fallback also failed:", fallbackError);
      }
    }
  }, []);

  // Fetch unread notifications count for admin
  useEffect(() => {
    if (user?.role === "admin" && token) {
      // เรียกดึงข้อมูล unread count และ badge counts ตอนโหลดหน้า
      fetchUnreadCount();
      fetchBadgeCounts();

      // ฟังก์ชันเมื่อได้รับออเดอร์ใหม่ → อัปเดตตัวเลข unread และ badge counts จาก database
      const handleNewOrder = (data, eventType) => {
        console.log("🔔 AdminLayout - New order received:", data, "Event type:", eventType);
        
        // Refresh unread count from database
        fetchUnreadCount();
        
        // Refresh badge counts from database เพื่อความแม่นยำ
        fetchBadgeCounts();
        
        console.log("🔄 Refreshing badge counts from database after new order");
      };

      // ไม่ต้องจัดการ status updates เพราะไม่สร้าง notification

      // ลงทะเบียน listener สำหรับ notification_update event
      const handleNotificationUpdate = () => {
        fetchUnreadCount();
        fetchBadgeCounts(); // Also refresh badge counts
      };

      // Create wrapper functions for cleanup
      const handleNewOrderWrapper = (data) => handleNewOrder(data, 'new_order');
      const handleNewGuestOrderWrapper = (data) => handleNewOrder(data, 'new_guest_order');

      // ลงทะเบียน listener (ไม่ต้องเชื่อมต่อ WebSocket ที่นี่ เพราะเชื่อมจาก AdminNotificationBridge แล้ว)
      websocketService.on("new_order", handleNewOrderWrapper);
      websocketService.on("new_guest_order", handleNewGuestOrderWrapper); // Add guest order handler
      // ไม่ฟัง status updates เพราะไม่สร้าง notification
      window.addEventListener("notification_update", handleNotificationUpdate);

      // ตรวจสอบ WebSocket connection แบบ simplified
      const checkWebSocketConnection = () => {
        if (
          !websocketService.ws ||
          websocketService.ws.readyState === WebSocket.CLOSED
        ) {
          websocketService.connect(token);
        }
      };

      // ตรวจสอบทันที
      checkWebSocketConnection();

      // ตรวจสอบอีกครั้งหลังจาก 2 วินาที (รวม 3 ครั้งเป็น 1 ครั้ง)
      const wsCheckTimeout = setTimeout(checkWebSocketConnection, 2000);

      // 🔄 เพิ่ม polling mechanism เป็น fallback (เพิ่มเวลาเป็น 60 วินาที)
      const pollingInterval = setInterval(() => {
        // เช็คว่า WebSocket ยังทำงานอยู่หรือไม่ ถ้าไม่ทำงานค่อย fetch
        if (!websocketService.isConnected()) {
          fetchUnreadCount();
        }
      }, 60000); // ทุก 60 วินาที

      // cleanup เมื่อ component unmount หรือ token เปลี่ยน
      return () => {
        websocketService.off("new_order", handleNewOrderWrapper);
        websocketService.off("new_guest_order", handleNewGuestOrderWrapper);
        // ไม่ต้อง cleanup status update listeners เพราะไม่ได้ลงทะเบียน
        window.removeEventListener(
          "notification_update",
          handleNotificationUpdate
        );
        clearInterval(pollingInterval);
        clearTimeout(wsCheckTimeout);
      };
    }
  }, [user?.role, token, fetchUnreadCount, fetchBadgeCounts]);

  // Function to update unread count (for use by children components)
  const updateUnreadCount = useCallback((newCount) => {
    setUnreadCount(newCount);
  }, []);

  // Function to decrease unread count by 1
  const decreaseUnreadCount = useCallback(() => {
    setUnreadCount((prev) => {
      const newCount = Math.max(0, prev - 1);
      return newCount;
    });
  }, []);

  // Functions for badge management
  const updateOrdersBadge = useCallback((count) => {
    console.log("🏷️ Updating orders badge count:", count);
    setOrdersBadgeCount(count);
  }, []);

  const updateGuestOrdersBadge = useCallback((count) => {
    console.log("🏷️ Updating guest orders badge count:", count);
    setGuestOrdersBadgeCount(count);
  }, []);

  const clearOrdersBadge = useCallback(() => {
    console.log("🧹 Clearing orders badge");
    setOrdersBadgeCount(0);
  }, []);

  const clearGuestOrdersBadge = useCallback(() => {
    console.log("🧹 Clearing guest orders badge");
    setGuestOrdersBadgeCount(0);
  }, []);

  // Context value
  const notificationContextValue = {
    unreadCount,
    updateUnreadCount,
    decreaseUnreadCount,
    fetchUnreadCount,
    fetchBadgeCounts, // Add this function to context
    // Badge management
    ordersBadgeCount,
    guestOrdersBadgeCount,
    updateOrdersBadge,
    updateGuestOrdersBadge,
    clearOrdersBadge,
    clearGuestOrdersBadge,
  };

  return (
    <NotificationContext.Provider value={notificationContextValue}>
      {!isPhoneOrdersPage && <AdminNotificationBridge />}
      <div className="min-h-screen bg-secondary-50">
        {/* Header */}
        <Header />

        <div className="flex pt-16">
          {/* Mobile menu button */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="lg:hidden fixed top-20 left-4 z-30 p-2 rounded-md bg-white shadow-lg text-secondary-600 hover:text-secondary-900 hover:bg-secondary-50"
          >
            {sidebarOpen ? (
              <FaTimes className="h-6 w-6" />
            ) : (
              <FaBars className="h-6 w-6" />
            )}
          </button>

          {/* Mobile overlay */}
          {sidebarOpen && (
            <div
              className="lg:hidden fixed inset-0 z-10 bg-black bg-opacity-50"
              onClick={() => setSidebarOpen(false)}
            />
          )}

          {/* Fixed Sidebar */}
          <aside
            className={`fixed left-0 top-16 w-64 h-screen bg-white shadow-lg z-20 overflow-y-auto transition-transform duration-300 ease-in-out lg:translate-x-0 ${
              sidebarOpen ? "translate-x-0" : "-translate-x-full"
            }`}
          >
            <nav className="p-4">
              <div className="space-y-2">
                <Link
                  to="/admin"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <FaChartBar className="h-6 w-6 mr-2" /> {translate('dashboard.title_admin')}
                </Link>
                <Link
                  to="/admin/users"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <FaUsers className="h-6 w-6 mr-2" /> {translate('admin.users')}
                </Link>
                <Link
                  to="/admin/restaurants"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <FaStore className="h-6 w-6 mr-2" /> {translate('admin.restaurants')}
                </Link>
                <Link
                  to="/admin/orders"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center justify-between px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <div className="flex items-center">
                    <FaUserCheck className="h-6 w-6 mr-2" /> {translate('admin.orders')}
                  </div>
                  {ordersBadgeCount > 0 && (
                    <span className="bg-orange-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center font-bold animate-pulse shadow-lg">
                      {ordersBadgeCount > 9 ? '9+' : ordersBadgeCount}
                    </span>
                  )}
                </Link>
                <Link
                  to="/admin/guest-orders"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center justify-between px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <div className="flex items-center">
                    <FaUserXmark  className="h-6 w-6 mr-2" /> {translate('admin.guest_orders')}
                  </div>
                  {guestOrdersBadgeCount > 0 && (
                    <span className="bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center font-bold animate-pulse shadow-lg">
                      {guestOrdersBadgeCount > 9 ? '9+' : guestOrdersBadgeCount}
                    </span>
                  )}
                </Link>
                <Link
                  to="/admin/phone-orders"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <BiSolidPhoneCall className="h-6 w-6 mr-2" /> {translate('admin.phone_orders_title')}
                </Link>
                <Link
                  to="/admin/create-phone-order"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <IoIosCreate  className="h-6 w-6 mr-2" /> {translate('admin.create_order_now')}
                </Link>
                <Link
                  to="/admin/categories"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <FaFolder className="h-6 w-6 mr-2" /> {translate('admin.categories')}
                </Link>
                <Link
                  to="/admin/advertisements"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <FaBullhorn className="h-6 w-6 mr-2" /> {translate('admin.manage_advertisements')}
                </Link>
                {/* <Link
                  to="/admin/analytics"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  📈 {translate('admin.reports_and_statistics')}
                </Link> */}
                <Link
                  to="/admin/settings"
                  onClick={() => setSidebarOpen(false)}
                  className="flex items-center px-4 py-2 text-secondary-700 rounded-lg hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <FaCog className="h-6 w-6 mr-2" /> {translate('admin.settings')}
                </Link>

              </div>
            </nav>
          </aside>

          {/* Main Content */}
          <main className="flex-1 lg:ml-64 min-h-screen">
            <div className="p-4 lg:p-8">{children}</div>
          </main>
        </div>


      </div>
    </NotificationContext.Provider>
  );
};

export default AdminLayout;
