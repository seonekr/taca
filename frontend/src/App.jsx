import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { CartProvider } from './contexts/CartContext';
import { GuestCartProvider } from './contexts/GuestCartContext';
import { DineInCartProvider } from './contexts/DineInCartContext';
import { LanguageProvider } from './contexts/LanguageContext';
import { RestaurantNotificationProvider } from './contexts/RestaurantNotificationContext';
import ProtectedRoute from './utils/ProtectedRoute';
import ErrorBoundary from './components/common/ErrorBoundary';

// Loading Component
const LoadingSpinner = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
  </div>
);

// Lazy load pages เพื่อลด initial bundle size
// Auth Pages
const Login = lazy(() => import('./pages/auth/Login'));
const Register = lazy(() => import('./pages/auth/Register'));
const VerifyEmail = lazy(() => import('./pages/auth/VerifyEmail'));
const ForgotPassword = lazy(() => import('./pages/auth/ForgotPassword'));

// Customer Pages - โหลดเฉพาะเมื่อต้องการ
const Home = lazy(() => import('./pages/customer/Home'));
const Categories = lazy(() => import('./pages/customer/Categories'));
const CategoryDetail = lazy(() => import('./pages/customer/CategoryDetail'));
const Restaurants = lazy(() => import('./pages/customer/Restaurants'));
const RestaurantDetail = lazy(() => import('./pages/customer/RestaurantDetail'));
const AllProducts = lazy(() => import('./pages/customer/AllProducts'));
const Search = lazy(() => import('./pages/customer/Search'));
const Profile = lazy(() => import('./pages/customer/Profile'));
const Notifications = lazy(() => import('./pages/customer/Notifications'));
const Cart = lazy(() => import('./pages/customer/Cart'));
const GuestCart = lazy(() => import('./pages/customer/GuestCart'));
const GuestOrders = lazy(() => import('./pages/customer/GuestOrders'));
const Orders = lazy(() => import('./pages/customer/Orders'));
const Settings = lazy(() => import('./pages/customer/Settings'));
const Contact = lazy(() => import('./pages/customer/Contact'));
const About = lazy(() => import('./pages/customer/About'));
const Help = lazy(() => import('./pages/customer/Help'));
const Terms = lazy(() => import('./pages/customer/Terms'));
const Privacy = lazy(() => import('./pages/customer/Privacy'));

// Restaurant Pages
const RestaurantDashboard = lazy(() => import('./pages/restaurant/RestaurantDashboard'));
const RestaurantOrders = lazy(() => import('./pages/restaurant/RestaurantOrders'));
const RestaurantProfile = lazy(() => import('./pages/restaurant/RestaurantProfile'));
const RestaurantTables = lazy(() => import('./pages/restaurant/RestaurantTables'));
const RestaurantDineInProducts = lazy(() => import('./pages/restaurant/RestaurantDineInProducts'));
const RestaurantReviews = lazy(() => import('./pages/restaurant/RestaurantReviews'));

// Dine-In Pages
const DineIn = lazy(() => import('./pages/customer/DineIn'));
const DineInCart = lazy(() => import('./pages/customer/DineInCart'));
const DineInOrderHistory = lazy(() => import('./pages/customer/DineInOrderHistory'));

// Admin Pages - โหลดเฉพาะเมื่อ admin เข้าใช้งาน
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'));
const AdminOrders = lazy(() => import('./pages/admin/AdminOrders'));
const AdminGuestOrders = lazy(() => import('./pages/admin/AdminGuestOrders'));
const CreatePhoneOrder = lazy(() => import('./pages/admin/CreatePhoneOrder'));
const PhoneOrders = lazy(() => import('./pages/admin/PhoneOrders'));
const AdminRestaurants = lazy(() => import('./pages/admin/AdminRestaurants'));
const AdminCategories = lazy(() => import('./pages/admin/AdminCategories'));
const AdminRestaurantProducts = lazy(() => import('./pages/admin/AdminRestaurantProducts'));
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers'));
const AdminSettings = lazy(() => import('./pages/admin/AdminSettings'));
const AdminAdvertisements = lazy(() => import('./pages/admin/AdminAdvertisements'));
// Layouts - โหลดทันทีเพราะใช้บ่อย
import CustomerLayout from './layouts/CustomerLayout';
import RestaurantLayout from './layouts/RestaurantLayout';
import AdminLayout from './layouts/AdminLayout';

// Error Pages - โหลดทันทีเพราะเป็น fallback
import NotFound from './pages/errors/NotFound';
import Unauthorized from './pages/errors/Unauthorized';

// ScrollToTop component
function ScrollToTop() {
  const { pathname } = useLocation();

  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}

function App() {
  return (
    <ErrorBoundary>
      <LanguageProvider>
        <AuthProvider>
          <RestaurantNotificationProvider>
            <CartProvider>
              <GuestCartProvider>
                <DineInCartProvider>
                <Router>
                  <ScrollToTop />
                  <div className="min-h-screen bg-secondary-50">
                    <Suspense fallback={<LoadingSpinner />}>
                      <Routes>
                    {/* Public Auth Routes */}
                    <Route path="/login" element={
                      <ProtectedRoute requireAuth={false}>
                        <Login />
                      </ProtectedRoute>
                    } />
                    <Route path="/register" element={
                      <ProtectedRoute requireAuth={false}>
                        <Register />
                      </ProtectedRoute>
                    } />
                    <Route path="/verify-email" element={
                      <ProtectedRoute requireAuth={false}>
                        <VerifyEmail />
                      </ProtectedRoute>
                    } />
                    <Route path="/forgot-password" element={
                      <ProtectedRoute requireAuth={false}>
                        <ForgotPassword />
                      </ProtectedRoute>
                    } />

                    {/* Guest Order Routes (No Login Required) */}
                    <Route path="/guest-cart" element={
                      <CustomerLayout>
                        <GuestCart />
                      </CustomerLayout>
                    } />

                    <Route path="/guest-orders" element={
                      <CustomerLayout>
                        <GuestOrders />
                      </CustomerLayout>
                    } />

                    {/* Dine-In QR Code Routes (No Login Required) */}
                    <Route path="/dine-in/:qrCodeData" element={
                      <CustomerLayout>
                        <DineIn />
                      </CustomerLayout>
                    } />

                    <Route path="/dine-in/:qrCodeData/cart" element={
                      <CustomerLayout>
                        <DineInCart />
                      </CustomerLayout>
                    } />

                    <Route path="/dine-in/:qrCodeData/history" element={
                      <CustomerLayout>
                        <DineInOrderHistory />
                      </CustomerLayout>
                    } />


                    {/* Customer Routes - Products as main page */}
                    <Route path="/" element={
                      <CustomerLayout>
                        <AllProducts />
                      </CustomerLayout>
                    } />

                    <Route path="/home" element={
                      <CustomerLayout>
                        <Home />
                      </CustomerLayout>
                    } />
                    
                    <Route path="/restaurants" element={
                      <CustomerLayout>
                        <Restaurants />
                      </CustomerLayout>
                    } />

                    <Route path="/restaurants/:id" element={
                      <CustomerLayout>
                        <RestaurantDetail />
                      </CustomerLayout>
                    } />

                    <Route path="/categories" element={
                      <CustomerLayout>
                        <Categories />
                      </CustomerLayout>
                    } />

                    <Route path="/categories/:id" element={
                      <CustomerLayout>
                        <CategoryDetail />
                      </CustomerLayout>
                    } />

                    <Route path="/products" element={
                      <CustomerLayout>
                        <AllProducts />
                      </CustomerLayout>
                    } />

                    <Route path="/search" element={
                      <CustomerLayout>
                        <Search />
                      </CustomerLayout>
                    } />

                    {/* Public Pages */}
                    <Route path="/about" element={
                      <CustomerLayout>
                        <About />
                      </CustomerLayout>
                    } />

                    <Route path="/contact" element={
                      <CustomerLayout>
                        <Contact />
                      </CustomerLayout>
                    } />

                    <Route path="/help" element={
                      <CustomerLayout>
                        <Help />
                      </CustomerLayout>
                    } />

                    <Route path="/terms" element={
                      <CustomerLayout>
                        <Terms />
                      </CustomerLayout>
                    } />

                    <Route path="/privacy" element={
                      <CustomerLayout>
                        <Privacy />
                      </CustomerLayout>
                    } />

                    {/* Customer Protected Routes */}
                    <Route path="/cart" element={
                      <ProtectedRoute allowedRoles={['customer']}>
                        <CustomerLayout>
                          <Cart />
                        </CustomerLayout>
                      </ProtectedRoute>
                    } />


                    <Route path="/orders" element={
                      <ProtectedRoute allowedRoles={['customer', 'general_restaurant', 'special_restaurant', 'admin']}>
                        <CustomerLayout>
                          <Orders />
                        </CustomerLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/profile" element={
                      <ProtectedRoute allowedRoles={['customer', 'general_restaurant', 'special_restaurant', 'admin']}>
                        <CustomerLayout>
                          <Profile />
                        </CustomerLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/notifications" element={
                      <ProtectedRoute allowedRoles={['customer', 'general_restaurant', 'special_restaurant', 'admin']}>
                        <CustomerLayout>
                          <Notifications />
                        </CustomerLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/settings" element={
                      <ProtectedRoute allowedRoles={['customer', 'general_restaurant', 'special_restaurant', 'admin']}>
                        <CustomerLayout>
                          <Settings />
                        </CustomerLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/favorites" element={
                      <ProtectedRoute allowedRoles={['customer']}>
                        <CustomerLayout>
                          <div className="container mx-auto px-4 py-8">
                            <h1 className="text-3xl font-bold text-secondary-800 mb-6">Favorite list</h1>
                            <div className="bg-white rounded-lg shadow-md p-8 text-center">
                              <div className="text-6xl mb-4 opacity-30">❤️</div>
                              <h2 className="text-xl font-semibold text-secondary-700 mb-2">No favorite list</h2>
                              <p className="text-secondary-500 mb-6">Add your favorite restaurant or menu to the favorite list</p>
                              <Link to="/restaurants" className="bg-primary-500 text-white px-6 py-3 rounded-lg hover:bg-primary-600 transition-colors inline-block">
                                Search for restaurant
                              </Link>
                            </div>
                          </div>
                        </CustomerLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/addresses" element={
                      <ProtectedRoute allowedRoles={['customer']}>
                        <CustomerLayout>
                          <div className="container mx-auto px-4 py-8">
                            <h1 className="text-3xl font-bold text-secondary-800 mb-6">My address</h1>
                            <div className="bg-white rounded-lg shadow-md p-8">
                              <div className="text-center mb-8">
                                <div className="text-6xl mb-4 opacity-30">📍</div>
                                <h2 className="text-xl font-semibold text-secondary-700 mb-2">No address</h2>
                                <p className="text-secondary-500 mb-6">Add your address for convenient delivery</p>
                                <button className="bg-primary-500 text-white px-6 py-3 rounded-lg hover:bg-primary-600 transition-colors">
                                  Add new address
                                </button>
                              </div>
                              <div className="border-t pt-6">
                                <p className="text-sm text-secondary-500 text-center">
                                  Feature to manage address is under development
                                </p>
                              </div>
                            </div>
                          </div>
                        </CustomerLayout>
                      </ProtectedRoute>
                    } />

                    {/* Restaurant Routes */}
                    <Route path="/restaurant" element={
                      <ProtectedRoute allowedRoles={['general_restaurant', 'special_restaurant', 'admin']}>
                        <RestaurantLayout>
                          <RestaurantDashboard />
                        </RestaurantLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/restaurant/orders" element={
                      <ProtectedRoute allowedRoles={['general_restaurant', 'special_restaurant', 'admin']}>
                        <RestaurantLayout>
                          <RestaurantOrders />
                        </RestaurantLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/restaurant/reviews" element={
                      <ProtectedRoute allowedRoles={['general_restaurant', 'special_restaurant', 'admin']}>
                        <RestaurantLayout>
                          <RestaurantReviews />
                        </RestaurantLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/restaurant/analytics" element={
                      <ProtectedRoute allowedRoles={['general_restaurant', 'special_restaurant', 'admin']}>
                        <RestaurantLayout>
                          <div className="p-8 text-center">
                            <h1 className="text-2xl font-bold">Restaurant analytics</h1>
                            <p className="text-secondary-600 mt-2">Under development...</p>
                          </div>
                        </RestaurantLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/restaurant/profile" element={
                      <ProtectedRoute allowedRoles={['general_restaurant', 'special_restaurant', 'admin']}>
                        <RestaurantLayout>
                          <RestaurantProfile />
                        </RestaurantLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/restaurant/tables" element={
                      <ProtectedRoute allowedRoles={['general_restaurant', 'special_restaurant', 'admin']}>
                        <RestaurantLayout>
                          <RestaurantTables />
                        </RestaurantLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/restaurant/dine-in-products" element={
                      <ProtectedRoute allowedRoles={['general_restaurant', 'special_restaurant', 'admin']}>
                        <RestaurantLayout>
                          <RestaurantDineInProducts />
                        </RestaurantLayout>
                      </ProtectedRoute>
                    } />

                    {/* Admin Routes */}
                    <Route path="/admin" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminDashboard />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/users" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminUsers />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/restaurants" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminRestaurants />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/restaurants/:restaurantId/products" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminRestaurantProducts />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/categories" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminCategories />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/orders" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminOrders />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/guest-orders" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminGuestOrders />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/create-phone-order" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <CreatePhoneOrder />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/phone-orders" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <PhoneOrders />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/analytics" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <div className="p-8 text-center">
                            <h1 className="text-2xl font-bold">Reports and statistics</h1>
                            <p className="text-secondary-600 mt-2">Under development...</p>
                          </div>
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/settings" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminSettings />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    <Route path="/admin/advertisements" element={
                      <ProtectedRoute allowedRoles={['admin']}>
                        <AdminLayout>
                          <AdminAdvertisements />
                        </AdminLayout>
                      </ProtectedRoute>
                    } />

                    {/* Error Routes */}
                    <Route path="/unauthorized" element={<Unauthorized />} />
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                  </Suspense>
                </div>
              </Router>
                </DineInCartProvider>
              </GuestCartProvider>
            </CartProvider>
          </RestaurantNotificationProvider>
        </AuthProvider>
      </LanguageProvider>
    </ErrorBoundary>
  );
}

export default App;
