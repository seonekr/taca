import React, { useState, useEffect, useRef } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { useCart } from "../../contexts/CartContext";
import { useGuestCart } from "../../contexts/GuestCartContext";
import { useLanguage } from "../../contexts/LanguageContext";
import { appSettingsService } from "../../services/api";
import LanguageSwitcher from "./LanguageSwitcher";
import { checkAndSync, hasOfflineData, getLastSyncedAt, checkHasNewVersion } from "../../utils/syncManager";
import {
  Bars3Icon,
  XMarkIcon,
  ShoppingCartIcon,
  BellIcon,
  UserIcon,
  HeartIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  ArrowDownTrayIcon,
  CheckCircleIcon,
  CloudArrowDownIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";

const Header = ({ appSettings: appSettingsProp }) => {
  const { user, isAuthenticated, logout } = useAuth();
  const { itemCount: cartItemCount } = useCart();
  const { itemCount: guestCartItemCount } = useGuestCart();
  const { translate } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();
  // const [isMenuOpen, setIsMenuOpen] = useState(false);
  // const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [appSettings, setAppSettings] = useState(appSettingsProp || null);
  // const profileMenuRef = useRef(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const dropdownRef = useRef(null);
  const searchInputRef = useRef(null);

  // Offline download button state
  // 'idle' | 'syncing' | 'done' | 'uptodate' | 'error'
  const [syncState, setSyncState] = useState("idle");
  const [lastSynced, setLastSynced] = useState(null);
  // Mobile: แสดงปุ่มเฉพาะเมื่อยังไม่มีข้อมูล หรือมีข้อมูลใหม่บน server
  const [mobileShowBtn, setMobileShowBtn] = useState(false);
  const syncTimerRef = useRef(null);

  const refreshMobileBtnVisibility = async () => {
    try {
      const hasNew = await checkHasNewVersion();
      setMobileShowBtn(hasNew);
      if (!hasNew) {
        const has = await hasOfflineData();
        if (has) {
          getLastSyncedAt().then((ts) => setLastSynced(ts));
          setSyncState("done");
        }
      }
    } catch {
      setMobileShowBtn(false);
    }
  };

  useEffect(() => {
    refreshMobileBtnVisibility();
    const onOnline = () => refreshMobileBtnVisibility();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDownloadOffline = async () => {
    if (syncState === "syncing") return;
    setSyncState("syncing");
    try {
      const synced = await checkAndSync();
      setSyncState(synced ? "done" : "uptodate");
      if (synced) {
        const ts = await getLastSyncedAt();
        setLastSynced(ts);
      }
      // ซ่อนปุ่ม mobile หลัง download สำเร็จ
      setMobileShowBtn(false);
      clearTimeout(syncTimerRef.current);
      syncTimerRef.current = setTimeout(() => setSyncState("done"), 3000);
    } catch {
      setSyncState("error");
      clearTimeout(syncTimerRef.current);
      syncTimerRef.current = setTimeout(() => {
        setSyncState("idle");
        setMobileShowBtn(true);
      }, 3000);
    }
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutsideDropdown = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutsideDropdown);
    return () =>
      document.removeEventListener("mousedown", handleClickOutsideDropdown);
  }, []);

  // Keep state in sync with prop
  useEffect(() => {
    if (appSettingsProp) {
      setAppSettings(appSettingsProp);
    }
  }, [appSettingsProp]);

  // Fetch app settings only if not provided by parent
  useEffect(() => {
    if (appSettingsProp) return;
    const fetchAppSettings = async () => {
      try {
        const response = await appSettingsService.getPublic();
        setAppSettings(response.data);
      } catch (error) {
        console.error("Error fetching app settings:", error);
      }
    };

    fetchAppSettings();
  }, [appSettingsProp]);

  // Close profile menu when clicking outside
  // useEffect(() => {
  //   const handleClickOutside = (event) => {
  //     if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) {
  //       setIsProfileMenuOpen(false);
  //     }
  //   };

  //   document.addEventListener('mousedown', handleClickOutside);
  //   return () => document.removeEventListener('mousedown', handleClickOutside);
  // }, []);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    setIsSearchOpen(false);
    setSearchQuery("");
    navigate(`/products?search=${encodeURIComponent(q)}`);
  };

  const toggleSearch = () => {
    setIsSearchOpen((prev) => {
      if (!prev) setTimeout(() => searchInputRef.current?.focus(), 50);
      return !prev;
    });
  };

  const handleLogout = async () => {
    const confirmed = window.confirm(
      translate("auth.confirm_logout") || "Are you sure you want to log out?"
    );
    if (!confirmed) return;

    await logout();
    navigate("/");
    setIsDropdownOpen(false);
  };

  const toggleDropdown = () => {
    setIsDropdownOpen(!isDropdownOpen);
  };

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  const getMenuItems = () => {
    if (!user) {
      return [
        {
          name: translate("common.home"),
          href: "/",
          current: location.pathname === "/",
        },
        {
          name: translate("nav.categories"),
          href: "/categories",
          current: location.pathname === "/categories",
        },
        {
          name: translate("nav.all_products"),
          href: "/products",
          current: location.pathname === "/products",
        },
        {
          name: translate("nav.orders"),
          href: "/guest-orders",
          current: location.pathname === "/guest-orders",
        }
        // { name: translate('common.about'), href: '/about', current: location.pathname === '/about' },
        // { name: translate('common.contact'), href: '/contact', current: location.pathname === '/contact' },
      ];
    }

    const baseItems = [
      {
        name: translate("common.home"),
        href: "/",
        current: location.pathname === "/",
      },
    ];

    if (user.role === "customer") {
      return [
        ...baseItems,
        // { name: translate('nav.restaurants'), href: '/restaurants', current: location.pathname === '/restaurants' },
        {
          name: translate("nav.categories"),
          href: "/categories",
          current: location.pathname === "/categories",
        },
        {
          name: translate("nav.all_products"),
          href: "/products",
          current: location.pathname === "/products",
        },
        {
          name: translate("nav.orders"),
          href: "/orders",
          current: location.pathname === "/orders",
        },
        // { name: translate('nav.favorites'), href: '/favorites', current: location.pathname === '/favorites' },
      ];
    } else if (user.role === "admin") {
      return [
        {
          name: translate("admin.role.admin"),
          href: "/admin",
          current: location.pathname.startsWith("/admin"),
        },
      ];
    } else if (
      user.role === "special_restaurant" ||
      user.role === "general_restaurant"
    ) {
      return [
        {
          name: translate("restaurant.my_restaurant") || "My Store",
          href: "/restaurant",
          current: location.pathname.startsWith("/restaurant"),
        },
        {
          name: translate("restaurant.orders"),
          href: "/restaurant/orders",
          current: location.pathname === "/restaurant/orders",
        },
      ];
    }

    return baseItems;
  };

  const getUserMenuItems = () => {
    const items = [
      { name: translate("common.profile"), href: "/profile" },
      { name: translate("common.settings"), href: "/settings" },
    ];

    if (user?.role === "customer") {
      items.splice(
        1,
        0,
        { name: translate("nav.orders"), href: "/orders" }
        // { name: translate('nav.favorites'), href: '/favorites' }
      );
    }

    return items;
  };

  const menuItems = getMenuItems();
  const userMenuItems = getUserMenuItems();

  // เลือก itemCount ตามสถานะการล็อกอิน
  const getItemCount = () => {
    if (isAuthenticated) {
      return cartItemCount;
    } else {
      return guestCartItemCount;
    }
  };

  const itemCount = getItemCount();
  
  // ซ่อน cart icon เมื่ออยู่ในหน้า dine-in (เพราะมี cart summary bar ด้านล่างแล้ว)
  const isDineInPage = location.pathname.startsWith('/dine-in/');
  const syncLabel = {
    idle: "บันทึกข้อมูล offline",

    syncing: "กำลังดาวน์โหลด...",
    done: lastSynced
      ? `อัปเดตล่าสุด ${new Date(lastSynced).toLocaleDateString("th-TH", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`
      : "บันทึกแล้ว",
    uptodate: "ข้อมูลเป็นปัจจุบันแล้ว",
    error: "ดาวน์โหลดล้มเหลว",
  }[syncState];

  const DownloadButton = ({ compact = false }) => (
    <button
      type="button"
      onClick={handleDownloadOffline}
      disabled={syncState === "syncing"}
      title={syncLabel}
      className={[
        "relative flex items-center gap-1.5 rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-primary-400",
        compact
          ? "p-1.5 text-secondary-500 hover:text-primary-600 hover:bg-primary-50"
          : "px-2.5 py-1.5 text-xs font-medium border text-secondary-600 hover:text-primary-700 hover:border-primary-300 hover:bg-primary-50 border-secondary-200 bg-white",
        syncState === "syncing" ? "opacity-60 cursor-wait" : "",
        syncState === "error" ? "text-red-500 border-red-300" : "",
      ].join(" ")}
      aria-label={syncLabel}
    >
      {/* Mobile compact: แสดง ↓ เสมอ (spinner เฉพาะตอน syncing) */}
      {compact ? (
        syncState === "syncing" ? (
          <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        ) : (
          <ArrowDownTrayIcon
            className={[
              "h-5 w-5",
              syncState === "done" || syncState === "uptodate" ? "text-green-500" : "",
              syncState === "error" ? "text-red-400" : "",
            ].join(" ")}
          />
        )
      ) : (
        /* Desktop: icon เปลี่ยนตาม state + ข้อความ */
        <>
          {syncState === "syncing" ? (
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          ) : syncState === "done" || syncState === "uptodate" ? (
            <CheckCircleIcon className="h-4 w-4 text-green-500" />
          ) : syncState === "error" ? (
            <CloudArrowDownIcon className="h-4 w-4 text-red-400" />
          ) : (
            <ArrowDownTrayIcon className="h-4 w-4" />
          )}
          <span>{syncLabel}</span>
        </>
      )}
    </button>
  );

  return (
    <header className="fixed top-0 left-0 right-0 z-[1100] bg-white shadow-lg border-b border-secondary-200">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 w-full">
          {/* Logo and Navigation */}
          <div className="flex items-center">
            <div className="flex-shrink-0 flex items-center">
              <Link 
                to={user?.role === "special_restaurant" || user?.role === "general_restaurant" ? "/restaurant" : "/"} 
                className="hidden md:flex items-center space-x-3"
              >
                {/* Logo */}
                {appSettings?.logo_url ? (
                  <img
                    src={appSettings.logo_url}
                    alt={appSettings.app_name || "FoodDelivery"}
                    className="h-10 w-auto"
                  />
                ) : (
                  <span className="text-2xl">🍕</span>
                )}
                {/* App Name - Hidden on mobile */}
                <span className="hidden sm:block text-2xl font-bold text-primary-600">
                  {appSettings?.app_name || "FoodDelivery"}
                </span>
              </Link>
            </div>

            {/* Desktop Navigation - Hidden on mobile */}
            <div className="hidden md:ml-6 md:flex md:space-x-8">
              {menuItems.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`${
                    item.current
                      ? "border-primary-500 text-secondary-900"
                      : "border-transparent text-secondary-500 hover:border-secondary-300 hover:text-secondary-700"
                  } inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium`}
                >
                  {item.name}
                </Link>
              ))}
            </div>
          </div>

          {/* Right side buttons */}
          <div className="flex items-center justify-end w-full md:w-auto space-x-2 md:space-x-4">
            {/* Search bar - desktop */}
            <div className="hidden md:flex items-center">
              {isSearchOpen ? (
                <form onSubmit={handleSearchSubmit} className="flex items-center">
                  <input
                    ref={searchInputRef}
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={translate("common.search") || "ค้นหา..."}
                    className="w-48 lg:w-64 px-3 py-1.5 text-sm border border-secondary-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-primary-400 focus:border-transparent"
                    onKeyDown={(e) => e.key === "Escape" && setIsSearchOpen(false)}
                  />
                  <button
                    type="submit"
                    className="px-3 py-1.5 bg-primary-500 text-white rounded-r-lg hover:bg-primary-600 transition-colors"
                  >
                    <MagnifyingGlassIcon className="h-4 w-4" />
                  </button>
                </form>
              ) : (
                <button
                  onClick={toggleSearch}
                  className="p-2 text-secondary-500 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                  title={translate("common.search") || "ค้นหา"}
                >
                  <MagnifyingGlassIcon className="h-5 w-5" />
                </button>
              )}
            </div>

            {/* Language Switcher + Download button - เฉพาะ desktop/tablet */}
            <div className="hidden md:flex items-center gap-1.5">
              <DownloadButton />
              <LanguageSwitcher />
            </div>

            {isAuthenticated ? (
              <div className="flex items-center space-x-4">
                {/* Customer specific icons - ซ่อนเมื่ออยู่ในหน้า dine-in */}
                {user?.role === "customer" && !isDineInPage && (
                  <>
                    <Link
                      to="/cart"
                      className="hidden md:block p-2 text-secondary-500 hover:text-secondary-700 relative"
                    >
                      <ShoppingCartIcon className="h-6 w-6" />
                      {/* Cart badge */}
                      {itemCount > 0 && (
                        <span className="absolute -top-1 -right-1 bg-primary-600 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
                          {itemCount > 99 ? "99+" : itemCount}
                        </span>
                      )}
                    </Link>

                    {/* <Link
                      to="/notifications"
                      className="p-2 text-secondary-500 hover:text-secondary-700 relative"
                    >
                      <BellIcon className="h-6 w-6" />
                      <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
                        3
                      </span>
                    </Link> */}
                  </>
                )}

                {/* Profile Menu - Hidden on mobile */}
                <div className="hidden md:block relative" ref={dropdownRef}>
                  <button
                    onClick={toggleDropdown}
                    className="flex items-center text-sm rounded-full text-secondary-400 hover:text-secondary-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                  >
                    <span className="sr-only">
                      {translate("common.profile")}
                    </span>
                    <div className="h-8 w-8 rounded-full bg-primary-500 flex items-center justify-center text-white font-medium">
                      {user?.username?.charAt(0).toUpperCase()}
                    </div>
                  </button>

                  {isDropdownOpen && (
                    <div className="origin-top-right absolute right-0 mt-2 w-48 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 z-50">
                      <div className="py-1" role="menu">
                        <div className="px-4 py-2 text-sm text-secondary-700 border-b">
                          <div className="font-medium">{user?.username}</div>
                          <div className="text-xs text-secondary-500">
                            {user?.email}
                          </div>
                        </div>
                        {userMenuItems.map((item) => (
                          <Link
                            key={item.name}
                            to={item.href}
                            className="block px-4 py-2 text-sm text-secondary-700 hover:bg-secondary-100"
                            role="menuitem"
                            onClick={() => setIsDropdownOpen(false)}
                          >
                            {item.name}
                          </Link>
                        ))}
                        <button
                          onClick={handleLogout}
                          className="block w-full text-left px-4 py-2 text-sm text-secondary-700 hover:bg-secondary-100"
                          role="menuitem"
                        >
                          {translate("common.logout")}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="hidden md:flex items-center space-x-4">
                {/* ซ่อน guest cart icon เมื่ออยู่ในหน้า dine-in */}
                {!isDineInPage && (
                <Link
                  to="/guest-cart"
                  className="text-secondary-700 hover:text-secondary-900 px-3 py-2 rounded-md text-sm font-medium relative"
                >
                  <ShoppingCartIcon className="h-6 w-6" />
                  {itemCount > 0 && (
                    <span className="absolute -top-1 -right-1 bg-primary-600 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
                      {itemCount > 99 ? "99+" : itemCount}
                    </span>
                  )}
                </Link>
                )}
                <Link
                  to="/login"
                  className="text-secondary-700 hover:text-secondary-900 px-3 py-2 rounded-md text-sm font-medium"
                >
                  {translate("common.login")}
                </Link>
                <Link
                  to="/register"
                  className="bg-primary-600 text-white hover:bg-primary-700 px-3 py-2 rounded-md text-sm font-medium"
                >
                  {translate("common.register")}
                </Link>
              </div>
            )}
            {/* Mobile: Download + Language + Menu ชิดกันทางขวา */}
            <div className="md:hidden flex items-center gap-1 ml-auto">
              <button
                onClick={toggleSearch}
                className="p-2 text-secondary-500 hover:text-primary-600 rounded-lg transition-colors"
              >
                <MagnifyingGlassIcon className="h-5 w-5" />
              </button>
              {mobileShowBtn && <DownloadButton compact />}
              <div className="block">
                <LanguageSwitcher />
              </div>
              {/* Mobile menu button - Hidden on mobile (using bottom navigation instead) และซ่อนในหน้า dine-in */}
              {!isDineInPage && (
              <div className="flex items-center">
              {/* Cart icon เฉพาะมือถือ ขยับมาชิดขวา */}
              {/* {user?.role === "customer" && (
              <Link
                to="/cart"
                className="p-2 text-secondary-500 hover:text-secondary-700 relative"
              >
                <ShoppingCartIcon className="h-7 w-7" />
                {itemCount > 0 && (
                  <span className="absolute -top-1 -right-1 bg-primary-600 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
                    {itemCount > 99 ? "99+" : itemCount}
                  </span>
                )}
              </Link>
              )} */}
              <button
                onClick={toggleMobileMenu}
                className="p-2 rounded-md text-secondary-400 hover:text-secondary-500 hover:bg-secondary-100 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500"
              >
                <span className="sr-only">Open main menu</span>
                {!isMobileMenuOpen ? (
                  <svg
                    className="block h-6 w-6"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 6h16M4 12h16M4 18h16"
                    />
                  </svg>
                ) : (
                  <svg
                    className="block h-6 w-6"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                )}
              </button>
              </div>
              )}
            </div>
          </div>
        </div>

        {/* Mobile search bar */}
        {isSearchOpen && (
          <div className="md:hidden px-4 pb-3">
            <form onSubmit={handleSearchSubmit} className="flex items-center">
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={translate("common.search") || "ค้นหา..."}
                className="flex-1 px-3 py-2 text-sm border border-secondary-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-primary-400"
                onKeyDown={(e) => e.key === "Escape" && setIsSearchOpen(false)}
                autoFocus
              />
              <button
                type="submit"
                className="px-4 py-2 bg-primary-500 text-white rounded-r-lg hover:bg-primary-600 transition-colors"
              >
                <MagnifyingGlassIcon className="h-5 w-5" />
              </button>
            </form>
          </div>
        )}

        {/* Mobile menu - ซ่อนในหน้า dine-in */}
        {isMobileMenuOpen && !isDineInPage && (
          <div className="md:hidden">
            <div className="pt-2 pb-3 space-y-1">
              {menuItems.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`${
                    item.current
                      ? "bg-primary-50 border-primary-500 text-primary-700"
                      : "border-transparent text-secondary-500 hover:bg-secondary-50 hover:border-secondary-300 hover:text-secondary-700"
                  } block pl-3 pr-4 py-2 border-l-4 text-base font-medium`}
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  {item.name}
                </Link>
              ))}
            </div>
            {user ? (
              <div className="pt-4 pb-3 border-t border-secondary-200">
                <div className="flex items-center px-4">
                  <div className="flex-shrink-0">
                    <div className="h-10 w-10 rounded-full bg-primary-500 flex items-center justify-center text-white font-medium">
                      {user.username?.charAt(0).toUpperCase()}
                    </div>
                  </div>
                  <div className="ml-3">
                    <div className="text-base font-medium text-secondary-800">
                      {user.username}
                    </div>
                    <div className="text-sm font-medium text-secondary-500">
                      {user.email}
                    </div>
                  </div>
                </div>
                <div className="mt-3 space-y-1">
                  {userMenuItems.map((item) => (
                    <Link
                      key={item.name}
                      to={item.href}
                      className="block px-4 py-2 text-base font-medium text-secondary-500 hover:text-secondary-800 hover:bg-secondary-100"
                      onClick={() => setIsMobileMenuOpen(false)}
                    >
                      {item.name}
                    </Link>
                  ))}
                  <button
                    onClick={() => {
                      handleLogout();
                      setIsMobileMenuOpen(false);
                    }}
                    className="block w-full text-left px-4 py-2 text-base font-medium text-secondary-500 hover:text-secondary-800 hover:bg-secondary-100"
                  >
                    {translate("common.logout")}
                  </button>
                </div>
              </div>
            ) : (
              <div className="pt-4 pb-3 border-t border-secondary-200">
                <div className="space-y-1">
                  <Link
                    to="/login"
                    className="block px-4 py-2 text-base font-medium text-secondary-500 hover:text-secondary-800 hover:bg-secondary-100"
                    onClick={() => setIsMobileMenuOpen(false)}
                  >
                    {translate("common.login")}
                  </Link>
                  <Link
                    to="/register"
                    className="block px-4 py-2 text-base font-medium text-secondary-500 hover:text-secondary-800 hover:bg-secondary-100"
                    onClick={() => setIsMobileMenuOpen(false)}
                  >
                    {translate("common.register")}
                  </Link>
                </div>
              </div>
            )}
          </div>
        )}
      </nav>
    </header>
  );
};

export default Header;
