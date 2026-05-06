import React, { useState, useEffect } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useCart } from "../../contexts/CartContext";
import { useGuestCart } from "../../contexts/GuestCartContext";
import { useAuth } from "../../contexts/AuthContext";
import api from "../../services/api";
import { useLanguage } from "../../contexts/LanguageContext";
import { formatPrice } from "../../utils/formatPrice";
import { getTranslatedName, getTranslatedDescription } from "../../utils/translationHelpers";
import { HomeIcon, ShoppingCartIcon, MagnifyingGlassIcon } from "@heroicons/react/24/outline";
import AdvertisementGallery from "./AdvertisementGallery";

const HOME_PAGE_LIMIT = 24;
const ALL_PRODUCTS_PAGE_SIZE = 24;

const AllProducts = () => {
  const { addItem: addToCart } = useCart();
  const { addItem: addToGuestCart } = useGuestCart();
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const searchQuery = searchParams.get("search") || "";
  const isHomePage = location.pathname === "/";

  const [products, setProducts] = useState([]);
  const [restaurants, setRestaurants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalProducts, setTotalProducts] = useState(0);
  const { translate, currentLanguage } = useLanguage();

  const addItem = isAuthenticated ? addToCart : addToGuestCart;

  useEffect(() => {
    setCurrentPage(1);
    fetchData();
  }, [isHomePage, searchQuery]);

  useEffect(() => {
    if (restaurants.length > 0) {
      fetchProducts(currentPage);
    }
  }, [currentPage, currentLanguage]);

  const fetchData = async () => {
    try {
      const restaurantsRes = await api.get("/restaurants/");
      setRestaurants(restaurantsRes.data.results || restaurantsRes.data);
      await fetchProducts(1);
    } catch (error) {
      console.error("Error fetching data:", error);
      setError("ERROR_LOADING_DATA");
    }
  };

  const fetchProducts = async (page = 1) => {
    try {
      if (products.length === 0 || currentPage !== page) {
        setLoading(true);
      }
      const pageSize = isHomePage ? HOME_PAGE_LIMIT : ALL_PRODUCTS_PAGE_SIZE;
      const params = new URLSearchParams();
      params.append("page", isHomePage ? 1 : page);
      params.append("page_size", pageSize);
      params.append("limit", pageSize);
      if (searchQuery) params.append("search", searchQuery);

      const response = await api.get(`/products/?${params.toString()}`);
      const data = response.data;

      if (data.results) {
        const items = isHomePage ? data.results.slice(0, HOME_PAGE_LIMIT) : data.results;
        setProducts(items);
        setTotalProducts(data.count || 0);
        setTotalPages(isHomePage ? 1 : Math.ceil((data.count || 0) / pageSize));
      } else {
        const allProducts = data || [];
        if (isHomePage) {
          setProducts(allProducts.slice(0, HOME_PAGE_LIMIT));
          setTotalProducts(allProducts.length || 0);
          setTotalPages(1);
        } else {
          const startIndex = (page - 1) * pageSize;
          setProducts(allProducts.slice(startIndex, startIndex + pageSize));
          setTotalProducts(allProducts.length || 0);
          setTotalPages(Math.ceil((allProducts.length || 0) / pageSize));
        }
      }
    } catch (error) {
      console.error("Error fetching products:", error);
      setError("ERROR_LOADING_PRODUCTS");
    } finally {
      setLoading(false);
    }
  };

  if (loading && products.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto"></div>
          <p className="mt-4 text-secondary-600">
            {translate("common.loading")}
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">
          <p className="text-red-500">
            {error === "ERROR_LOADING_DATA"
              ? translate("common.failed_to_load_data")
              : error === "ERROR_LOADING_PRODUCTS"
              ? translate("common.failed_to_load_products")
              : error}
          </p>
          <button
            onClick={() => {
              setError(null);
              fetchData();
            }}
            className="mt-4 bg-primary-500 text-white px-4 py-2 rounded-lg hover:bg-primary-600"
          >
            {translate("common.try_again")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <AdvertisementGallery />

      <div className="container mx-auto px-4 py-8">
      {searchQuery && (
        <div className="mb-4 flex items-center gap-2 text-sm text-secondary-600">
          <MagnifyingGlassIcon className="h-4 w-4" />
          <span>{translate("common.search_results_for") || "ผลการค้นหา:"} <strong>"{searchQuery}"</strong></span>
          <Link to="/products" className="ml-2 text-primary-500 hover:text-primary-700 underline">
            {translate("common.clear_search") || "ล้างการค้นหา"}
          </Link>
        </div>
      )}
      {products.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-2 sm:gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {products.map((product) => (
              <div
                key={product.product_id}
                className={`bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 overflow-hidden flex sm:block p-1 sm:p-0 ${
                  restaurants.find(
                    (r) =>
                      (r.restaurant_id === product.restaurant_id ||
                        r.restaurant_id === product.restaurant?.restaurant_id ||
                        r.restaurant_id === product.restaurant?.id ||
                        r.restaurant_id === product.restaurant) &&
                      r.status === "closed"
                  )
                    ? "opacity-75"
                    : ""
                }`}
              >
                <div className="relative h-20 w-20 sm:h-48 sm:w-full bg-gray-200 flex-shrink-0 rounded-lg sm:rounded-none">
                  {product.image_display_url || product.image ? (
                    <img
                      src={product.image_display_url || product.image}
                      alt={product.product_name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.target.style.display = "none";
                        e.target.nextSibling.style.display = "flex";
                      }}
                    />
                  ) : null}
                  <div
                    className={
                      "w-full h-full flex items-center justify-center " +
                      (product.image_display_url || product.image
                        ? "hidden"
                        : "")
                    }
                  >
                    <div className="text-6xl opacity-30">🍽️</div>
                  </div>

                  {/* ตรวจสอบสถานะร้านก่อน แล้วค่อยแสดงสถานะสินค้า */}
                  {(() => {
                    const restaurant = restaurants.find(
                      (r) =>
                        r.restaurant_id === product.restaurant_id ||
                        r.restaurant_id === product.restaurant?.restaurant_id ||
                        r.restaurant_id === product.restaurant?.id ||
                        r.restaurant_id === product.restaurant
                    );

                    if (restaurant?.status === "closed") {
                      return (
                        <div className="absolute inset-0 bg-black bg-opacity-60 flex items-center justify-center">
                          <div className="text-center">
                            <span className="text-white font-semibold text-lg block">
                              {translate("common.closed")}
                            </span>
                            <span className="text-white/80 text-sm">
                              {restaurant.restaurant_name}
                            </span>
                          </div>
                        </div>
                      );
                    } else if (!product.is_available) {
                      return (
                        <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center">
                          <span className="text-white font-semibold">
                            {translate("common.not_available")}
                          </span>
                        </div>
                      );
                    }
                    return null;
                  })()}
                </div>

                <div className="p-2 sm:p-4 flex-1 flex flex-col sm:block">
                  <div className="flex justify-between items-center mb-2 sm:mb-2">
                    <div className="flex-1">
                      <h3 className="font-semibold text-secondary-800 text-sm sm:text-base leading-tight hover:text-primary-600 transition-colors">
                        {getTranslatedName(product, currentLanguage, product.product_name)}
                      </h3>

                      <span className="text-primary-500 font-bold text-sm sm:text-lg">
                        {formatPrice(product.price || 0)}
                      </span>
                    </div>
                    <div className="flex flex-col gap-1 ml-2 sm:hidden">
                      {/* ปุ่มดูร้านนี้ - ไอคอนเฉพาะมือถือ */}
                      <Link
                        to={`/restaurants/${
                          product.restaurant_id ||
                          product.restaurant?.restaurant_id ||
                          product.restaurant?.id ||
                          product.restaurant
                        }`}
                        className="py-1 px-6 bg-secondary-100 text-secondary-700 text-center rounded-lg font-medium hover:bg-secondary-200 transition-colors"
                      >
                        <HomeIcon className="w-3 h-3" />
                      </Link>

                      {/* ปุ่มเพิ่มลงตะกร้า - ไอคอนเฉพาะมือถือ */}
                      {(() => {
                        const restaurant = restaurants.find(
                          (r) =>
                            r.restaurant_id === product.restaurant_id ||
                            r.restaurant_id ===
                              product.restaurant?.restaurant_id ||
                            r.restaurant_id === product.restaurant?.id ||
                            r.restaurant_id === product.restaurant
                        );

                        const isRestaurantClosed =
                          restaurant?.status === "closed";
                        const isProductUnavailable = !product.is_available;

                        return (
                          <button
                            onClick={() => {
                              if (isRestaurantClosed || isProductUnavailable)
                                return;

                              const restaurantData = {
                                id: restaurant.restaurant_id,
                                name: restaurant.restaurant_name,
                                address: restaurant.address,
                                phone_number: restaurant.phone_number,
                                status: restaurant.status,
                              };

                              const productData = {
                                ...product,
                                restaurant_status: restaurant.status,
                              };

                              const result = addItem(
                                productData,
                                restaurantData
                              );

                              if (result && result.success === false) {
                                if (result.requiresLogin) return;
                                alert(
                                  result.error ||
                                    translate("common.error_adding_to_cart")
                                );
                                return;
                              }

                              alert(
                                translate("common.added_to_cart", {
                                  product: getTranslatedName(product, currentLanguage, product.product_name),
                                })
                              );
                            }}
                            className={`py-1 px-6 rounded-lg font-semibold transition-colors ${
                              isRestaurantClosed || isProductUnavailable
                                ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                                : "bg-primary-500 text-white hover:bg-primary-600"
                            }`}
                            disabled={
                              isRestaurantClosed || isProductUnavailable
                            }
                          >
                            <ShoppingCartIcon className="w-3 h-3" />
                          </button>
                        );
                      })()}
                    </div>
                  </div>

                  <p className="hidden sm:block text-secondary-600 text-sm mb-3 line-clamp-2">
                    {getTranslatedDescription(product, currentLanguage, product.description) || product.description || translate("common.no_description")}
                  </p>

                  <div className="hidden sm:flex items-center justify-between mb-2">
                    <span className="text-xs text-secondary-500">
                      {product.restaurant_name ||
                        product.restaurant?.restaurant_name ||
                        product.restaurant?.name ||
                        translate("common.restaurant")}
                    </span>
                  </div>

                  {product.category && (
                    <div className="hidden sm:block mb-3">
                      <span className="px-2 py-1 bg-secondary-100 text-secondary-700 text-xs rounded-full">
                        {getTranslatedName(product.category, currentLanguage, product.category.category_name)}
                      </span>
                    </div>
                  )}

                  {/* ปุ่มสำหรับหน้าจอใหญ่ */}
                  <div className="hidden sm:flex flex-row gap-2 justify-center">
                    {(() => {
                      const restaurant = restaurants.find(
                        (r) =>
                          r.restaurant_id === product.restaurant_id ||
                          r.restaurant_id ===
                            product.restaurant?.restaurant_id ||
                          r.restaurant_id === product.restaurant?.id ||
                          r.restaurant_id === product.restaurant
                      );

                      const isRestaurantClosed =
                        restaurant?.status === "closed";
                      const isProductUnavailable = !product.is_available;

                      return (
                        <>
                          {/* ปุ่มดูร้านนี้ - ข้อความเต็มสำหรับหน้าจอใหญ่ */}
                          <Link
                            to={`/restaurants/${
                              product.restaurant_id ||
                              product.restaurant?.restaurant_id ||
                              product.restaurant?.id ||
                              product.restaurant
                            }`}
                            className="py-2 px-6 bg-secondary-100 text-secondary-700 text-center rounded-lg font-medium hover:bg-secondary-200 transition-colors text-sm"
                          >
                            {translate("common.view_this_restaurant")}
                          </Link>

                          {/* ปุ่มเพิ่มลงตะกร้า - ข้อความเต็มสำหรับหน้าจอใหญ่ */}
                          <button
                            onClick={() => {
                              if (isRestaurantClosed || isProductUnavailable)
                                return;

                              const restaurantData = {
                                id: restaurant.restaurant_id,
                                name: restaurant.restaurant_name,
                                address: restaurant.address,
                                phone_number: restaurant.phone_number,
                                status: restaurant.status,
                              };

                              const productData = {
                                ...product,
                                restaurant_status: restaurant.status,
                              };

                              const result = addItem(
                                productData,
                                restaurantData
                              );

                              if (result && result.success === false) {
                                if (result.requiresLogin) return;
                                alert(
                                  result.error ||
                                    translate("common.error_adding_to_cart")
                                );
                                return;
                              }

                              alert(
                                translate("common.added_to_cart", {
                                  product: getTranslatedName(product, currentLanguage, product.product_name),
                                })
                              );
                            }}
                            className={`py-2 px-8 rounded-lg font-semibold transition-colors ${
                              isRestaurantClosed || isProductUnavailable
                                ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                                : "bg-primary-500 text-white hover:bg-primary-600"
                            }`}
                            disabled={
                              isRestaurantClosed || isProductUnavailable
                            }
                          >
                            {isRestaurantClosed
                              ? translate("common.closed")
                              : isProductUnavailable
                              ? translate("common.not_available")
                              : translate("cart.add")}
                          </button>
                        </>
                      );
                    })()}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* View All button on home page */}
          {isHomePage && (
            <div className="mt-8 flex justify-center">
              <Link
                to="/products"
                className="px-8 py-3 bg-primary-500 text-white rounded-lg font-semibold hover:bg-primary-600 transition-colors"
              >
                {translate("common.view_all_products") || "ดูสินค้าทั้งหมด"}
              </Link>
            </div>
          )}

          {/* Pagination - only on /products page */}
          {!isHomePage && totalPages > 1 && (
            <div className="mt-8 flex justify-center">
              <div className="flex items-center space-x-2">
                {/* Previous Button */}
                <button
                  onClick={() =>
                    setCurrentPage((prev) => Math.max(prev - 1, 1))
                  }
                  disabled={currentPage === 1}
                  className={`px-3 py-2 rounded-lg ${
                    currentPage === 1
                      ? "bg-secondary-200 text-secondary-400 cursor-not-allowed"
                      : "bg-white border border-secondary-300 text-secondary-700 hover:bg-secondary-50"
                  }`}
                >
                  {translate("common.previous")}
                </button>

                {/* Page Numbers */}
                {Array.from({ length: Math.min(totalPages, 5) }, (_, index) => {
                  let pageNumber;
                  if (totalPages <= 5) {
                    pageNumber = index + 1;
                  } else if (currentPage <= 3) {
                    pageNumber = index + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNumber = totalPages - 4 + index;
                  } else {
                    pageNumber = currentPage - 2 + index;
                  }

                  return (
                    <button
                      key={pageNumber}
                      onClick={() => setCurrentPage(pageNumber)}
                      className={`px-3 py-2 rounded-lg ${
                        currentPage === pageNumber
                          ? "bg-primary-500 text-white"
                          : "bg-white border border-secondary-300 text-secondary-700 hover:bg-secondary-50"
                      }`}
                    >
                      {pageNumber}
                    </button>
                  );
                })}

                {/* Next Button */}
                <button
                  onClick={() =>
                    setCurrentPage((prev) => Math.min(prev + 1, totalPages))
                  }
                  disabled={currentPage === totalPages}
                  className={`px-3 py-2 rounded-lg ${
                    currentPage === totalPages
                      ? "bg-secondary-200 text-secondary-400 cursor-not-allowed"
                      : "bg-white border border-secondary-300 text-secondary-700 hover:bg-secondary-50"
                  }`}
                >
                  {translate("common.next")}
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-12">
          <div className="text-6xl mb-4 opacity-30">🍽️</div>
          <h3 className="text-xl font-semibold text-secondary-700 mb-2">
            {translate("common.no_products_found")}
          </h3>
          <p className="text-secondary-500 mb-6">
            {translate("common.try_changing_the_search_or_filter")}
          </p>
          <button
            onClick={() => {
              setCurrentPage(1);
              fetchProducts(1);
            }}
            className="bg-primary-500 text-white px-6 py-3 rounded-lg hover:bg-primary-600 transition-colors"
          >
            {translate("common.try_again")}
          </button>
        </div>
      )}
      </div>
    </div>
  );
};

export default AllProducts;
