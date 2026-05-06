import React, { useState, useEffect, useRef } from 'react';
import * as XLSX from 'xlsx';
import { useLanguage } from '../../contexts/LanguageContext';
import { FcGallery } from "react-icons/fc";
import {
  FaTheaterMasks,
  FaStar,
  FaSearch,
  FaTrash,
  FaPlus,
  FaTimes,
  FaImage,
  FaUpload,
  FaArrowUp,
  FaArrowDown,
  FaMapMarkerAlt,
  FaPhone,
  FaClock,
  FaChevronUp,
  FaChevronDown,
  FaFileExcel,
  FaDownload,
  FaCheckCircle,
  FaExclamationTriangle,
  FaSpinner,
} from 'react-icons/fa';
import { entertainmentVenueService, venueCategoryService, countryService, cityService } from '../../services/api';
import { getTranslatedName, getTranslatedDescription } from '../../utils/translationHelpers';
import MapPicker from '../../components/maps/MapPicker';
import AddressPickerLeaflet from '../../components/maps/AddressPickerLeaflet';

const AdminEntertainmentVenues = () => {
  const { translate, availableLanguages, currentLanguage } = useLanguage();
  const [venues, setVenues] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line no-unused-vars
  const [error, setError] = useState(null);
  const [searchInput, setSearchInput] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 20;
  const [selectedVenue, setSelectedVenue] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [modalType, setModalType] = useState('view'); // 'view', 'edit', 'create', 'gallery'
  const [showGalleryModal, setShowGalleryModal] = useState(false);
  /** รายการในโมดัลแกลเลอรี: รูปจากเซิร์ฟเวอร์ + รูปรออัปโหลด (มี file + previewUrl) */
  const [galleryDraft, setGalleryDraft] = useState([]);
  const [gallerySaving, setGallerySaving] = useState(false);

  // --- Excel Import ---
  const [showImportModal, setShowImportModal] = useState(false);
  /** ขั้นตอน: 'idle' | 'preview' | 'importing' | 'done' */
  const [importStep, setImportStep] = useState('idle');
  /** แถวที่ parse มาจาก Excel */
  const [importRows, setImportRows] = useState([]);
  /** venue_name (lowercase) ที่ซ้ำกันภายในไฟล์ Excel */
  const [importDuplicateNames, setImportDuplicateNames] = useState(new Set());
  /** { success: [], failed: [] } */
  const [importResult, setImportResult] = useState(null);
  const [exportingExcel, setExportingExcel] = useState(false);
  const importFileRef = useRef(null);
  /** ซ่อนแผนที่ชั่วคราวเพื่อเลื่อนฟอร์มโดยไม่ให้แผนที่ดัก scroll / zoom */
  const [venueMapExpanded, setVenueMapExpanded] = useState(true);
  const [userLocation, setUserLocation] = useState(null);
  const [countriesList, setCountriesList] = useState([]);
  const [citiesList, setCitiesList] = useState([]);
  const [formData, setFormData] = useState({
    venue_name: '',
    description: '',
    address: '',
    country: '',
    city: '',
    latitude: '',
    longitude: '',
    phone_number: '',
    opening_hours: '',
    category: null,
    status: 'open',
    image: null,
    translations: {},
  });

  // client-side search filter + pagination (ไม่เรียก API ทุกครั้งที่พิมพ์)
  const filteredVenues = venues.filter((v) => {
    if (!searchInput.trim()) return true;
    const q = searchInput.trim().toLowerCase();
    return (
      (v.venue_name || '').toLowerCase().includes(q) ||
      (v.description || '').toLowerCase().includes(q) ||
      (v.category_name || '').toLowerCase().includes(q) ||
      (v.address || '').toLowerCase().includes(q)
    );
  });
  const totalPages = Math.ceil(filteredVenues.length / PAGE_SIZE);
  const paginatedVenues = filteredVenues.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const fetchVenues = async () => {
    try {
      setLoading(true);
      setError(null);
      const params = { page_size: 500 };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (typeFilter !== 'all') params.category = typeFilter;

      const response = await entertainmentVenueService.getAll(params);
      const fetchedVenues = response.data?.results || response.data || [];
      setVenues(Array.isArray(fetchedVenues) ? fetchedVenues : []);
    } catch (err) {
      console.error('Error fetching venues:', err);
      setError(err.response?.data?.detail || err.message || translate('entertainment.load_error') || 'เกิดข้อผิดพลาดในการโหลดข้อมูล');
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await venueCategoryService.getAll();
      setCategories(response.data?.results || response.data || []);
    } catch (err) {
      console.error('Error fetching categories:', err);
    }
  };

  useEffect(() => {
    fetchCategories();
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setUserLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => {}
      );
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await countryService.getAll();
        const list = res.data?.results || res.data || [];
        if (!cancelled) setCountriesList(Array.isArray(list) ? list : []);
      } catch (e) {
        console.error(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!formData.country) {
      setCitiesList([]);
      return undefined;
    }
    (async () => {
      try {
        const res = await cityService.getAll({ country: formData.country });
        const list = res.data?.results || res.data || [];
        if (!cancelled) setCitiesList(Array.isArray(list) ? list : []);
      } catch (e) {
        console.error(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [formData.country]);

  useEffect(() => {
    if (showModal && modalType !== 'view') {
      setVenueMapExpanded(true);
    }
  }, [showModal, modalType]);

  // reset to page 1 when search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchInput]);

  useEffect(() => {
    fetchVenues();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, typeFilter, currentLanguage]);


  const handleCreate = () => {
    setFormData({
      venue_name: '',
      description: '',
      address: '',
      country: '',
      city: '',
      latitude: '',
      longitude: '',
      phone_number: '',
      opening_hours: '',
      category: null,
      status: 'open',
      image: null,
      translations: {},
    });
    setModalType('create');
    setShowModal(true);
  };

  const handleEdit = async (venue) => {
    let fullVenue = venue;
    try {
      const response = await entertainmentVenueService.getById(venue.venue_id, { allLanguages: true });
      fullVenue = response.data;
    } catch (err) {
      console.error('Error fetching venue details:', err);
    }

    const translations = {};
    if (fullVenue.translations) {
      fullVenue.translations.forEach(trans => {
        translations[trans.language_code] = {
          name: trans.translated_name || '',
          description: trans.translated_description || '',
        };
      });
    }

    setFormData({
      venue_name: fullVenue.venue_name || '',
      description: fullVenue.description || '',
      address: fullVenue.address || '',
      country: fullVenue.country != null && fullVenue.country !== '' ? String(fullVenue.country) : '',
      city: fullVenue.city != null && fullVenue.city !== '' ? String(fullVenue.city) : '',
      latitude: fullVenue.latitude || '',
      longitude: fullVenue.longitude || '',
      phone_number: fullVenue.phone_number || '',
      opening_hours: fullVenue.opening_hours || '',
      category: fullVenue.category || null,
      status: fullVenue.status || 'open',
      image: null,
      translations,
    });
    setSelectedVenue(fullVenue);
    setModalType('edit');
    setShowModal(true);
  };

  const handleView = (venue) => {
    setSelectedVenue(venue);
    setModalType('view');
    setShowModal(true);
  };

  const handleDelete = async (venue) => {
    if (window.confirm(translate('entertainment.delete_confirm') || `ยืนยันการลบ "${venue.venue_name}"?`)) {
      try {
        await entertainmentVenueService.delete(venue.venue_id);
        await fetchVenues();
        alert(translate('entertainment.delete_success') || 'ลบสถานที่สำเร็จ');
      } catch (err) {
        console.error('Error deleting venue:', err);
        alert(err.response?.data?.detail || err.message || translate('entertainment.save_error') || 'เกิดข้อผิดพลาดในการลบสถานที่');
      }
    }
  };

  const revokeGalleryDraftPreviews = (items) => {
    items.forEach((it) => {
      if (it.previewUrl) {
        try {
          URL.revokeObjectURL(it.previewUrl);
        } catch {
          /* ignore */
        }
      }
    });
  };

  const closeGalleryModal = () => {
    setGalleryDraft((prev) => {
      revokeGalleryDraftPreviews(prev);
      return [];
    });
    setShowGalleryModal(false);
  };

  const handleManageGallery = async (venue) => {
    setSelectedVenue(venue);
    try {
      const response = await entertainmentVenueService.getImages(venue.venue_id);
      const list = response.data || [];
      setGalleryDraft(
        list.map((img, idx) => ({
          ...img,
          _key: `save-${img.image_id}`,
          sort_order: Number(img.sort_order) || idx + 1,
        }))
      );
      setShowGalleryModal(true);
    } catch (err) {
      console.error('Error fetching images:', err);
      setGalleryDraft([]);
      setShowGalleryModal(true);
    }
  };

  /** เลือกไฟล์ = แสดงตัวอย่างเท่านั้น ยังไม่อัปโหลดจนกว่าจะกดบันทึก */
  const handleAddGalleryFiles = (e) => {
    const files = Array.from(e.target.files || []);
    const inputEl = e.target;
    if (files.length === 0) return;

    setGalleryDraft((prev) => {
      const sorted = [...prev].sort((a, b) => a.sort_order - b.sort_order);
      const start = sorted.length;
      const additions = files.map((file, i) => ({
        _key: `local-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 9)}`,
        file,
        previewUrl: URL.createObjectURL(file),
        caption: '',
        sort_order: start + i + 1,
        image_id: null,
      }));
      const combined = [...sorted, ...additions];
      return combined.map((item, idx) => ({ ...item, sort_order: idx + 1 }));
    });
    if (inputEl) inputEl.value = '';
  };

  const handleDeleteGalleryItem = async (draftKey) => {
    const item = galleryDraft.find((x) => x._key === draftKey);
    if (!item) return;

    if (item.file) {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      setGalleryDraft((prev) => {
        const next = prev.filter((x) => x._key !== draftKey);
        return next.map((it, idx) => ({ ...it, sort_order: idx + 1 }));
      });
      return;
    }

    if (!selectedVenue) return;
    if (!window.confirm(translate('entertainment.delete_image') || 'ยืนยันการลบรูปภาพนี้?')) {
      return;
    }
    try {
      await entertainmentVenueService.deleteImage(selectedVenue.venue_id, item.image_id);
      setGalleryDraft((prev) => {
        const next = prev.filter((x) => x._key !== draftKey);
        return next.map((it, idx) => ({ ...it, sort_order: idx + 1 }));
      });
      alert(translate('entertainment.delete_image_success') || 'ลบรูปภาพสำเร็จ');
    } catch (err) {
      console.error('Error deleting image:', err);
      alert(err.response?.data?.detail || err.message || translate('entertainment.delete_image_error') || 'เกิดข้อผิดพลาดในการลบรูปภาพ');
    }
  };

  const handleUpdateGalleryCaption = (draftKey, caption) => {
    setGalleryDraft((prev) =>
      prev.map((img) => (img._key === draftKey ? { ...img, caption } : img))
    );
  };

  const handleMoveGalleryItem = (draftKey, direction) => {
    setGalleryDraft((prev) => {
      const sorted = [...prev].sort((a, b) => a.sort_order - b.sort_order);
      const index = sorted.findIndex((x) => x._key === draftKey);
      if (index === -1) return prev;
      const next = [...sorted];
      if (direction === 'up' && index > 0) {
        [next[index - 1], next[index]] = [next[index], next[index - 1]];
      } else if (direction === 'down' && index < next.length - 1) {
        [next[index], next[index + 1]] = [next[index + 1], next[index]];
      } else {
        return prev;
      }
      return next.map((img, idx) => ({ ...img, sort_order: idx + 1 }));
    });
  };

  const handleSaveGallery = async () => {
    if (!selectedVenue) return;

    setGallerySaving(true);
    try {
      const sorted = [...galleryDraft].sort((a, b) => a.sort_order - b.sort_order);
      const imagesData = [];

      for (let i = 0; i < sorted.length; i++) {
        const item = sorted[i];
        if (item.file) {
          const formDataUpload = new FormData();
          formDataUpload.append('image', item.file);
          formDataUpload.append('caption', item.caption || '');
          const response = await entertainmentVenueService.uploadImage(
            selectedVenue.venue_id,
            formDataUpload
          );
          imagesData.push({
            image_id: response.data.image_id,
            caption: item.caption || '',
            sort_order: i + 1,
            is_primary: response.data.is_primary || item.is_primary || false,
          });
          if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
        } else {
          imagesData.push({
            image_id: item.image_id,
            caption: item.caption || '',
            sort_order: i + 1,
            is_primary: item.is_primary || false,
          });
        }
      }

      await entertainmentVenueService.batchUpdateImages(selectedVenue.venue_id, imagesData);
      alert(translate('entertainment.save_gallery_success') || 'บันทึกรูปภาพสำเร็จ');
      setGalleryDraft([]);
      setShowGalleryModal(false);
      await fetchVenues();
    } catch (err) {
      console.error('Error saving gallery:', err);
      alert(err.response?.data?.detail || err.message || translate('entertainment.save_gallery_error') || 'เกิดข้อผิดพลาดในการบันทึกรูปภาพ');
    } finally {
      setGallerySaving(false);
    }
  };

  const handleSave = async () => {
    try {
      // Prepare data for API
      const dataToSend = { ...formData };
      
      // Convert empty strings to null for optional fields
      if (dataToSend.latitude === '') dataToSend.latitude = null;
      if (dataToSend.longitude === '') dataToSend.longitude = null;
      if (dataToSend.phone_number === '') dataToSend.phone_number = null;
      if (dataToSend.opening_hours === '') dataToSend.opening_hours = null;
      if (dataToSend.description === '') dataToSend.description = null;
      if (dataToSend.country === '' || dataToSend.country == null) {
        dataToSend.country = null;
      } else {
        dataToSend.country = parseInt(dataToSend.country, 10);
      }
      if (dataToSend.city === '' || dataToSend.city == null) {
        dataToSend.city = null;
      } else {
        dataToSend.city = parseInt(dataToSend.city, 10);
      }
      
      // Convert category to integer if it's a string
      if (dataToSend.category && typeof dataToSend.category === 'string') {
        dataToSend.category = parseInt(dataToSend.category) || null;
      }
      
      // Convert latitude/longitude to number if they're strings and round to 12 decimal places
      if (dataToSend.latitude && typeof dataToSend.latitude === 'string') {
        const lat = parseFloat(dataToSend.latitude);
        if (!isNaN(lat)) {
          // Round to 12 decimal places
          dataToSend.latitude = Math.round(lat * 1e12) / 1e12;
        } else {
          dataToSend.latitude = null;
        }
      }
      if (dataToSend.longitude && typeof dataToSend.longitude === 'string') {
        const lng = parseFloat(dataToSend.longitude);
        if (!isNaN(lng)) {
          // Round to 12 decimal places
          dataToSend.longitude = Math.round(lng * 1e12) / 1e12;
        } else {
          dataToSend.longitude = null;
        }
      }
      // Also round if they're already numbers
      if (typeof dataToSend.latitude === 'number' && !isNaN(dataToSend.latitude)) {
        dataToSend.latitude = Math.round(dataToSend.latitude * 1e12) / 1e12;
      }
      if (typeof dataToSend.longitude === 'number' && !isNaN(dataToSend.longitude)) {
        dataToSend.longitude = Math.round(dataToSend.longitude * 1e12) / 1e12;
      }
      
      // Filter out empty translations
      const validTranslations = {};
      Object.keys(dataToSend.translations || {}).forEach(langCode => {
        const t = dataToSend.translations[langCode];
        if (t && t.name && t.name.trim()) {
          validTranslations[langCode] = { name: t.name.trim(), description: t.description || '' };
        }
      });
      dataToSend.translations = validTranslations;

      if (modalType === 'create') {
        await entertainmentVenueService.create(dataToSend);
        alert(translate('entertainment.add_success') || 'เพิ่มสถานที่สำเร็จ');
      } else if (modalType === 'edit') {
        await entertainmentVenueService.partialUpdate(selectedVenue.venue_id, dataToSend);
        alert(translate('entertainment.edit_success') || 'แก้ไขสถานที่สำเร็จ');
      }
      setShowModal(false);
      await fetchVenues();
    } catch (err) {
      console.error('Error saving venue:', err);
      const errorMessage = err.response?.data?.detail || 
                          (typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message) ||
                          translate('entertainment.save_error') || 'เกิดข้อผิดพลาดในการบันทึกข้อมูล';
      alert(errorMessage);
    }
  };

  const getUniqueCategories = () =>
    categories.map((c) => ({ id: c.category_id, name: c.category_name }));

  // ─── Excel Import ────────────────────────────────────────────────────────────

  const EXCEL_COLUMNS = [
    'venue_name', 'country_name', 'city_name',
    'address', 'latitude', 'longitude',
    'phone_number', 'opening_hours', 'description', 'status', 'category',
  ];

  const handleDownloadDatabaseExcel = async () => {
    setExportingExcel(true);
    try {
      const allVenues = [];
      let page = 1;
      let hasNext = true;
      const pageSize = 300;

      while (hasNext) {
        const response = await entertainmentVenueService.getAll({
          page,
          page_size: pageSize,
          ordering: 'venue_name',
        });
        const payload = response.data;
        const rows = Array.isArray(payload) ? payload : (payload?.results || []);

        if (Array.isArray(rows) && rows.length > 0) {
          allVenues.push(...rows);
        }

        if (Array.isArray(payload)) {
          hasNext = false;
        } else {
          hasNext = Boolean(payload?.next);
          if (hasNext) page += 1;
        }

        if (!rows.length) hasNext = false;
        if (page > 500) hasNext = false;
      }

      const mappedRows = allVenues.map((v) => ({
        venue_name: v.venue_name || '',
        country_name: v.country_name || '',
        city_name: v.city_name || '',
        address: v.address || '',
        latitude: v.latitude ?? '',
        longitude: v.longitude ?? '',
        phone_number: v.phone_number || '',
        opening_hours: v.opening_hours || '',
        description: v.description || '',
        status: ['open', 'closed'].includes(v.status) ? v.status : 'open',
        category: v.category_name || '',
      }));

      const sheetData = [
        EXCEL_COLUMNS,
        ...mappedRows.map((row) => EXCEL_COLUMNS.map((col) => row[col] ?? '')),
      ];

      const ws = XLSX.utils.aoa_to_sheet(sheetData);
      ws['!cols'] = EXCEL_COLUMNS.map((key) => {
        if (key === 'description') return { wch: 36 };
        if (['venue_name', 'address'].includes(key)) return { wch: 28 };
        return { wch: 18 };
      });

      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Venues');
      const dateSuffix = new Date().toISOString().slice(0, 10);
      XLSX.writeFile(wb, `entertainment_venues_export_${dateSuffix}.xlsx`);
    } catch (err) {
      console.error('Error exporting venues excel:', err);
      alert(
        err.response?.data?.detail ||
          err.message ||
          (translate('common.error') || 'เกิดข้อผิดพลาด')
      );
    } finally {
      setExportingExcel(false);
    }
  };

  const handleImportFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const wb = XLSX.read(evt.target.result, { type: 'binary' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const raw = XLSX.utils.sheet_to_json(ws, { defval: '' });

        const rows = raw.map((r, idx) => {
          const row = {};
          EXCEL_COLUMNS.forEach((col) => {
            row[col] = String(r[col] ?? '').trim();
          });
          return { _row: idx + 2, ...row };
        }).filter((r) => r.venue_name);

        const nameCounts = {};
        rows.forEach((r) => {
          const key = r.venue_name.toLowerCase();
          nameCounts[key] = (nameCounts[key] || 0) + 1;
        });
        const dupNames = new Set(
          Object.entries(nameCounts).filter(([, c]) => c > 1).map(([k]) => k)
        );

        setImportRows(rows);
        setImportDuplicateNames(dupNames);
        setImportStep('preview');
        setImportResult(null);
      } catch (err) {
        alert((translate('entertainment.import_read_error') || 'ไม่สามารถอ่านไฟล์ Excel ได้') + ': ' + err.message);
      }
    };
    reader.readAsBinaryString(file);
    if (importFileRef.current) importFileRef.current.value = '';
  };

  const handleRunImport = async () => {
    if (importRows.length === 0) return;
    setImportStep('importing');

    const payload = importRows.map((r) => ({
      venue_name: r.venue_name,
      country_name: r.country_name || '',
      city_name: r.city_name || '',
      address: r.address || '',
      latitude: r.latitude !== '' ? r.latitude : null,
      longitude: r.longitude !== '' ? r.longitude : null,
      phone_number: r.phone_number || '',
      opening_hours: r.opening_hours || '',
      description: r.description || '',
      status: ['open', 'closed'].includes(r.status) ? r.status : 'open',
      category_name: r.category || '',
    }));

    try {
      const response = await entertainmentVenueService.bulkCreate(payload);
      setImportResult(response.data);
      setImportStep('done');
      await fetchVenues();
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || translate('common.error') || 'เกิดข้อผิดพลาด';
      alert((translate('entertainment.import_run_error') || 'นำเข้าล้มเหลว') + ': ' + detail);
      setImportStep('preview');
    }
  };

  const resetImportModal = () => {
    setShowImportModal(false);
    setImportStep('idle');
    setImportRows([]);
    setImportDuplicateNames(new Set());
    setImportResult(null);
    if (importFileRef.current) importFileRef.current.value = '';
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-center items-center h-64">
          <div className="h-12 w-12 animate-spin rounded-full border-2 border-secondary-200 border-b-secondary-500" />
          <span className="ml-4 text-lg">{translate('common.loading') || 'กำลังโหลด...'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-2 sm:px-4 py-4 sm:py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold text-secondary-800">
          <FaTheaterMasks className="mr-2 inline-block h-6 w-6 text-secondary-600 sm:h-7 sm:w-7 md:h-8 md:w-8" aria-hidden /> {translate('entertainment.manage_venues') || 'จัดการสถานที่บันเทิง'}
        </h1>
        <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
          <button
            type="button"
            onClick={handleDownloadDatabaseExcel}
            disabled={exportingExcel}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-green-600 bg-white px-4 py-2 text-green-700 transition-colors hover:bg-green-50 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
          >
            {exportingExcel ? (
              <FaSpinner className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <FaDownload className="h-4 w-4" aria-hidden />
            )}
            <span>
              {translate('entertainment.download_template') || 'ดาวน์โหลด Excel'}
            </span>
          </button>
          <button
            type="button"
            onClick={() => { setShowImportModal(true); setImportStep('idle'); }}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-green-600 bg-white px-4 py-2 text-green-700 transition-colors hover:bg-green-50 sm:w-auto"
          >
            <FaFileExcel className="h-4 w-4" aria-hidden />
            <span>{translate('entertainment.import_excel') || 'นำเข้า Excel'}</span>
          </button>
          <button
            type="button"
            onClick={handleCreate}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-secondary-300 bg-secondary-800 px-4 py-2 text-white transition-colors hover:bg-secondary-900 sm:w-auto"
          >
            <FaPlus className="h-5 w-5" aria-hidden />
            <span>{translate('entertainment.add_venue') || 'เพิ่มสถานที่'}</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow-md p-4 sm:p-6 mb-4 sm:mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-secondary-700 mb-2">
              {translate('common.search') || 'ค้นหา'}
            </label>
            <div className="relative">
              <FaSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-400" aria-hidden />
              <input
                type="text"
                placeholder={translate('entertainment.search_placeholder') || 'ค้นหาชื่อ, คำอธิบาย, หมวดหมู่...'}
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-secondary-700 mb-2">
              {translate('entertainment.status_filter') || 'สถานะ'}
            </label>
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1); }}
              className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
            >
              <option value="all">{translate('common.all') || 'ทั้งหมด'}</option>
              <option value="open">{translate('common.open') || 'เปิด'}</option>
              <option value="closed">{translate('common.closed') || 'ปิด'}</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-secondary-700 mb-2">
              {translate('entertainment.category_filter') || 'หมวดหมู่'}
            </label>
            <select
              value={typeFilter}
              onChange={(e) => { setTypeFilter(e.target.value); setCurrentPage(1); }}
              className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
            >
              <option value="all">{translate('common.all') || 'ทั้งหมด'}</option>
              {getUniqueCategories().map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Venues Table - Desktop */}
      <div className="hidden lg:block bg-white rounded-lg shadow-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-secondary-200">
            <thead className="bg-secondary-50">
              <tr>
                <th className="px-4 xl:px-6 py-3 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider">
                  {translate('entertainment.image_header') || 'รูปภาพ'}
                </th>
                <th className="px-4 xl:px-6 py-3 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider">
                  {translate('entertainment.venue_name_header') || 'ชื่อสถานที่'}
                </th>
                <th className="px-4 xl:px-6 py-3 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider">
                  {translate('entertainment.category_header') || 'หมวดหมู่'}
                </th>
                <th className="px-4 xl:px-6 py-3 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider">
                  {translate('entertainment.status_header') || 'สถานะ'}
                </th>
                <th className="px-4 xl:px-6 py-3 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider">
                  {translate('entertainment.rating_header') || 'เรตติ้ง'}
                </th>
                <th className="px-4 xl:px-6 py-3 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider">
                  {translate('entertainment.created_date_header') || 'วันที่สร้าง'}
                </th>
                <th className="px-4 xl:px-6 py-3 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider">
                  {translate('admin.table.actions') || translate('entertainment.actions_header') || 'การจัดการ'}
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-secondary-200">
              {paginatedVenues.length > 0 ? (
                paginatedVenues.map((venue) => (
                  <tr key={venue.venue_id} className="hover:bg-secondary-50">
                    <td className="px-4 xl:px-6 py-4 whitespace-nowrap">
                      <div className="h-12 w-12 xl:h-16 xl:w-16 rounded-lg overflow-hidden bg-secondary-200">
                        {venue.image_display_url ? (
                          <img
                            src={venue.image_display_url}
                            alt={venue.venue_name}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="h-full w-full flex items-center justify-center text-xl xl:text-2xl text-secondary-400">
                            <FaTheaterMasks className="h-8 w-8 xl:h-10 xl:w-10" />
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-4 xl:px-6 py-4">
                      <div className="text-sm font-medium text-secondary-900">
                        {getTranslatedName(venue, currentLanguage, venue.venue_name)}
                      </div>
                      <div className="text-xs xl:text-sm text-secondary-500 line-clamp-1">
                        {getTranslatedDescription(venue, currentLanguage, venue.description)}
                      </div>
                    </td>
                    <td className="px-4 xl:px-6 py-4 whitespace-nowrap">
                      <span className="rounded px-2 py-1 text-xs font-medium bg-secondary-100 text-secondary-700">
                        {venue.category_name || '—'}
                      </span>
                    </td>
                    <td className="px-4 xl:px-6 py-4 whitespace-nowrap">
                      <span
                        className={`rounded px-2 py-1 text-xs font-medium ${
                          venue.status === 'open'
                            ? 'border border-emerald-100/80 bg-emerald-50/90 text-emerald-900'
                            : 'border border-slate-200 bg-slate-100 text-slate-600'
                        }`}
                      >
                        {venue.status === 'open' ? translate('common.open') || 'เปิด' : translate('common.closed') || 'ปิด'}
                      </span>
                    </td>
                    <td className="px-4 xl:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <FaStar className="mr-1 text-xs text-secondary-500" aria-hidden />
                        <span className="text-xs xl:text-sm font-medium">
                          {Number(venue.average_rating || 0).toFixed(1)}
                        </span>
                        <span className="text-xs xl:text-sm text-secondary-500 ml-1">
                          ({venue.total_reviews || 0})
                        </span>
                      </div>
                    </td>
                    <td className="px-4 xl:px-6 py-4 whitespace-nowrap text-xs xl:text-sm text-secondary-500">
                      {new Date(venue.created_at).toLocaleDateString('th-TH')}
                    </td>
                    <td className="px-4 xl:px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => handleView(venue)}
                          className="text-blue-600 hover:text-blue-900"
                        >
                          {translate('admin.action.view')}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleManageGallery(venue)}
                          className="text-emerald-600 hover:text-emerald-900"
                        >
                          {translate('entertainment.manage_images') || translate('admin.action.upload_image')}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleEdit(venue)}
                          className="text-indigo-600 hover:text-indigo-900"
                        >
                          {translate('admin.action.edit')}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(venue)}
                          className="font-medium text-red-600 hover:text-red-900"
                          title={translate('admin.action.delete')}
                        >
                          {translate('admin.action.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="7" className="px-6 py-8 text-center text-secondary-500">
                    {translate('entertainment.no_data') || 'ไม่พบข้อมูล'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination - Desktop */}
      {filteredVenues.length > PAGE_SIZE && (
        <div className="hidden lg:flex items-center justify-between bg-white rounded-b-lg border-t border-secondary-200 px-6 py-3 shadow-md">
          <span className="text-sm text-secondary-600">
            แสดง {Math.min((currentPage - 1) * PAGE_SIZE + 1, filteredVenues.length)}–{Math.min(currentPage * PAGE_SIZE, filteredVenues.length)} จาก {filteredVenues.length} รายการ
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => p - 1)}
              className="rounded-lg border border-secondary-300 px-3 py-1.5 text-sm font-medium text-secondary-700 hover:bg-secondary-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              ← ก่อนหน้า
            </button>
            <span className="text-sm font-medium text-secondary-700">
              หน้า {currentPage} / {totalPages}
            </span>
            <button
              type="button"
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage((p) => p + 1)}
              className="rounded-lg border border-secondary-300 px-3 py-1.5 text-sm font-medium text-secondary-700 hover:bg-secondary-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              ถัดไป →
            </button>
          </div>
        </div>
      )}

      {/* Venues Cards - Mobile/Tablet */}
      <div className="lg:hidden space-y-4">
        {paginatedVenues.length > 0 ? (
          paginatedVenues.map((venue) => (
            <div
              key={venue.venue_id}
              className="bg-white rounded-lg shadow-md p-4 hover:shadow-lg transition-shadow"
            >
              <div className="flex gap-4">
                <div className="flex-shrink-0">
                  <div className="h-20 w-20 sm:h-24 sm:w-24 rounded-lg overflow-hidden bg-secondary-200">
                    {venue.image_display_url ? (
                      <img
                        src={venue.image_display_url}
                        alt={venue.venue_name}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="h-full w-full flex items-center justify-center text-2xl text-secondary-400">
                        <FaTheaterMasks className="h-10 w-10" />
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-base sm:text-lg font-semibold text-secondary-900 mb-1 truncate">
                    {getTranslatedName(venue, currentLanguage, venue.venue_name)}
                  </h3>
                  <p className="text-xs sm:text-sm text-secondary-500 line-clamp-2 mb-2">
                    {getTranslatedDescription(venue, currentLanguage, venue.description)}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span
                      className={`rounded px-2 py-1 text-xs font-medium ${
                        venue.status === 'open'
                          ? 'border border-emerald-100/80 bg-emerald-50/90 text-emerald-900'
                          : 'border border-slate-200 bg-slate-100 text-slate-600'
                      }`}
                    >
                      {venue.status === 'open' ? translate('common.open') || 'เปิด' : translate('common.closed') || 'ปิด'}
                    </span>
                    <div className="flex items-center">
                      <FaStar className="mr-1 text-xs text-secondary-500" aria-hidden />
                      <span className="text-xs font-medium">
                        {Number(venue.average_rating || 0).toFixed(1)}
                      </span>
                      <span className="text-xs text-secondary-500 ml-1">
                        ({venue.total_reviews || 0})
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => handleView(venue)}
                      className="text-xs text-blue-600 hover:text-blue-900 sm:text-sm"
                    >
                      {translate('admin.action.view')}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleManageGallery(venue)}
                      className="text-xs text-emerald-600 hover:text-emerald-900 sm:text-sm"
                    >
                      {translate('entertainment.manage_images') || translate('admin.action.upload_image')}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleEdit(venue)}
                      className="text-xs text-indigo-600 hover:text-indigo-900 sm:text-sm"
                    >
                      {translate('admin.action.edit')}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(venue)}
                      className="text-xs font-medium text-red-600 hover:text-red-900 sm:text-sm"
                    >
                      {translate('admin.action.delete')}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="bg-white rounded-lg shadow-md p-8 text-center">
            <p className="text-secondary-500">{translate('entertainment.no_data') || 'ไม่พบข้อมูล'}</p>
          </div>
        )}
      </div>

      {/* Pagination - Mobile/Tablet */}
      {filteredVenues.length > PAGE_SIZE && (
        <div className="lg:hidden flex items-center justify-between bg-white rounded-lg shadow-md px-4 py-3 mt-2">
          <button
            type="button"
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => p - 1)}
            className="rounded-lg border border-secondary-300 px-3 py-1.5 text-sm font-medium text-secondary-700 hover:bg-secondary-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ← ก่อนหน้า
          </button>
          <span className="text-sm text-secondary-600">
            หน้า {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            disabled={currentPage >= totalPages}
            onClick={() => setCurrentPage((p) => p + 1)}
            className="rounded-lg border border-secondary-300 px-3 py-1.5 text-sm font-medium text-secondary-700 hover:bg-secondary-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ถัดไป →
          </button>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-[1200] flex items-start justify-center overflow-y-auto bg-black/50 p-2 pt-20 pb-8 sm:p-4 sm:pt-24">
          <div className="relative z-[1210] my-auto w-full max-w-4xl rounded-lg bg-white shadow-xl max-h-[min(90vh,calc(100vh-5rem))] overflow-y-auto">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white p-4 sm:p-6">
              <h2 className="text-lg sm:text-xl md:text-2xl font-bold text-secondary-800 pr-2">
                {modalType === 'create'
                  ? translate('entertainment.add_venue_title') || 'เพิ่มสถานที่บันเทิง'
                  : modalType === 'edit'
                  ? translate('entertainment.edit_venue_title') || 'แก้ไขสถานที่บันเทิง'
                  : translate('entertainment.venue_details_title') || 'รายละเอียดสถานที่'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="text-secondary-400 hover:text-secondary-600 flex-shrink-0"
              >
                <FaTimes className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />
              </button>
            </div>

            <div className="p-4 sm:p-6">
              {modalType === 'view' && selectedVenue ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.venue_name_label') || 'ชื่อสถานที่'}
                      </label>
                      <p className="text-secondary-900">{getTranslatedName(selectedVenue, currentLanguage, selectedVenue.venue_name)}</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.category_label') || 'หมวดหมู่'}
                      </label>
                      <p className="text-secondary-900">{selectedVenue.category_name || '—'}</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.status_label') || 'สถานะ'}
                      </label>
                      <span
                        className={`rounded px-2 py-1 text-xs font-medium ${
                          selectedVenue.status === 'open'
                            ? 'border border-emerald-100/80 bg-emerald-50/90 text-emerald-900'
                            : 'border border-slate-200 bg-slate-100 text-slate-600'
                        }`}
                      >
                        {selectedVenue.status === 'open' ? translate('common.open') || 'เปิด' : translate('common.closed') || 'ปิด'}
                      </span>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.rating_label') || 'เรตติ้ง'}
                      </label>
                      <div className="flex items-center">
                        <FaStar className="mr-1 text-secondary-500" aria-hidden />
                        <span>{Number(selectedVenue.average_rating || 0).toFixed(1)}</span>
                        <span className="text-secondary-500 ml-1">
                          ({selectedVenue.total_reviews || 0} {translate('entertainment.reviews_label') || 'รีวิว'})
                        </span>
                      </div>
                    </div>
                    <div className="col-span-2">
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.description_label') || 'คำอธิบาย'}
                      </label>
                      <p className="text-secondary-900">{getTranslatedDescription(selectedVenue, currentLanguage, selectedVenue.description)}</p>
                    </div>
                    <div className="col-span-2">
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        <FaMapMarkerAlt className="inline mr-1" />
                        {translate('entertainment.address_label') || 'ที่อยู่'}
                      </label>
                      <p className="text-secondary-900">{selectedVenue.address}</p>
                    </div>
                    {(selectedVenue.country_name || selectedVenue.country) && (
                      <div>
                        <label className="block text-sm font-medium text-secondary-700 mb-1">
                          {translate('common.country') || 'ประเทศ'}
                        </label>
                        <p className="text-secondary-900">
                          {selectedVenue.country_name || selectedVenue.country || '—'}
                        </p>
                      </div>
                    )}
                    {(selectedVenue.city_name || selectedVenue.city) && (
                      <div>
                        <label className="block text-sm font-medium text-secondary-700 mb-1">
                          {translate('common.city') || 'เมือง'}
                        </label>
                        <p className="text-secondary-900">
                          {selectedVenue.city_name || selectedVenue.city || '—'}
                        </p>
                      </div>
                    )}
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        <FaPhone className="inline mr-1" />
                        {translate('entertainment.phone_label') || 'เบอร์โทร'}
                      </label>
                      <p className="text-secondary-900">{selectedVenue.phone_number}</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        <FaClock className="inline mr-1" />
                        {translate('entertainment.opening_hours_label') || 'เวลาเปิด-ปิด'}
                      </label>
                      <p className="text-secondary-900">{selectedVenue.opening_hours}</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.latitude_label') || 'ละติจูด'}
                      </label>
                      <p className="text-secondary-900">{selectedVenue.latitude}</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.longitude_label') || 'ลองจิจูด'}
                      </label>
                      <p className="text-secondary-900">{selectedVenue.longitude}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <form className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.venue_name_label') || 'ชื่อสถานที่'} *
                      </label>
                      <input
                        type="text"
                        value={formData.venue_name}
                        onChange={(e) =>
                          setFormData({ ...formData, venue_name: e.target.value })
                        }
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.category_label') || 'หมวดหมู่'}
                      </label>
                      <select
                        value={formData.category || ''}
                        onChange={(e) =>
                          setFormData({ ...formData, category: e.target.value || null })
                        }
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
                      >
                        <option value="">-- {translate('entertainment.category') || 'เลือกหมวดหมู่'} --</option>
                        {categories.map((cat) => (
                          <option key={cat.category_id} value={cat.category_id}>
                            {cat.category_name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="col-span-2">
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.description_label') || 'คำอธิบาย'}
                      </label>
                      <textarea
                        value={formData.description}
                        onChange={(e) =>
                          setFormData({ ...formData, description: e.target.value })
                        }
                        rows="3"
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
                      />
                    </div>

                    {/* Translations */}
                    {availableLanguages && availableLanguages.filter(lang => lang.code !== 'en').length > 0 && (
                      <div className="col-span-2">
                        <h4 className="text-sm font-medium text-secondary-800 mb-3">
                          {translate('admin.product_modal.translations_title') || 'การแปลภาษา'}
                        </h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {availableLanguages.filter(lang => lang.code !== 'en').map(lang => (
                            <div key={lang.code} className="p-4 border border-secondary-200 rounded-lg bg-secondary-50">
                              <h5 className="text-sm font-medium text-secondary-700 mb-3 flex items-center">
                                <span className="w-6 h-6 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center text-xs font-bold mr-2">
                                  {lang.code.toUpperCase()}
                                </span>
                                {translate(`admin.language_${lang.code}`) || lang.name}
                              </h5>
                              <div className="mb-2">
                                <label className="block text-xs text-secondary-600 mb-1">
                                  {translate('entertainment.venue_name_label') || 'ชื่อสถานที่'}
                                </label>
                                <input
                                  type="text"
                                  value={formData.translations[lang.code]?.name || ''}
                                  onChange={(e) => setFormData({
                                    ...formData,
                                    translations: {
                                      ...formData.translations,
                                      [lang.code]: {
                                        ...formData.translations[lang.code],
                                        name: e.target.value,
                                      },
                                    },
                                  })}
                                  placeholder={`${translate('entertainment.venue_name_label') || 'ชื่อสถานที่'} (${lang.code.toUpperCase()})`}
                                  className="w-full p-2 border border-secondary-300 rounded text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-secondary-600 mb-1">
                                  {translate('entertainment.description_label') || 'คำอธิบาย'}
                                </label>
                                <textarea
                                  value={formData.translations[lang.code]?.description || ''}
                                  onChange={(e) => setFormData({
                                    ...formData,
                                    translations: {
                                      ...formData.translations,
                                      [lang.code]: {
                                        ...formData.translations[lang.code],
                                        description: e.target.value,
                                      },
                                    },
                                  })}
                                  placeholder={`${translate('entertainment.description_label') || 'คำอธิบาย'} (${lang.code.toUpperCase()})`}
                                  rows={2}
                                  className="w-full p-2 border border-secondary-300 rounded text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                        <p className="text-xs text-secondary-500 mt-2">
                          {translate('admin.product_modal.translations_optional_hint') || 'ไม่บังคับ — หากไม่กรอก จะแสดงชื่อภาษาอังกฤษแทน'}
                        </p>
                      </div>
                    )}

                    <div className="col-span-2">
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.address_label') || 'ที่อยู่'} *
                      </label>
                      <AddressPickerLeaflet
                        value={formData.address}
                        onChange={(v) => setFormData((prev) => ({ ...prev, address: v }))}
                        onLocationSelect={(loc) => {
                          setFormData((prev) => ({
                            ...prev,
                            address: loc.address || prev.address,
                            latitude: String(loc.lat),
                            longitude: String(loc.lng),
                          }));
                        }}
                        placeholder={
                          translate('entertainment.address_search_placeholder') ||
                          'Type place name, address, coordinates or Plus Code'
                        }
                        referenceLocation={
                          formData.latitude && formData.longitude
                            ? { lat: parseFloat(formData.latitude), lng: parseFloat(formData.longitude) }
                            : (userLocation || { lat: 17.97, lng: 102.63 })
                        }
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('common.country') || 'ประเทศ'}
                      </label>
                      <select
                        value={formData.country}
                        onChange={(e) =>
                          setFormData({ ...formData, country: e.target.value, city: '' })
                        }
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80 bg-white"
                      >
                        <option value="">{translate('common.select_country') || '— เลือกประเทศ —'}</option>
                        {countriesList.map((c) => (
                          <option key={c.country_id} value={String(c.country_id)}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('common.city') || 'เมือง'}
                      </label>
                      <select
                        value={formData.city}
                        onChange={(e) =>
                          setFormData({ ...formData, city: e.target.value })
                        }
                        disabled={!formData.country}
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80 bg-white disabled:bg-secondary-50"
                      >
                        <option value="">{translate('common.select_city') || '— เลือกเมือง —'}</option>
                        {citiesList.map((c) => (
                          <option key={c.city_id} value={String(c.city_id)}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    {/* Location Picker */}
                    <div className="md:col-span-2">
                      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                        <label className="block text-sm font-medium text-secondary-700">
                          {translate('entertainment.location_label') || 'ตำแหน่งสถานที่'}
                        </label>
                        <button
                          type="button"
                          onClick={() => setVenueMapExpanded((v) => !v)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-secondary-300 bg-white px-3 py-1.5 text-xs font-medium text-secondary-700 transition hover:bg-secondary-50 sm:text-sm"
                        >
                          {venueMapExpanded ? (
                            <>
                              <FaChevronUp className="h-3.5 w-3.5" aria-hidden />
                              {translate('entertainment.hide_map') || 'ซ่อนแผนที่'}
                            </>
                          ) : (
                            <>
                              <FaChevronDown className="h-3.5 w-3.5" aria-hidden />
                              {translate('entertainment.show_map') || 'แสดงแผนที่'}
                            </>
                          )}
                        </button>
                      </div>

                      {venueMapExpanded ? (
                        <>
                          <MapPicker
                            showPlaceSearch={false}
                            initialCenter={{
                              lat: formData.latitude ? parseFloat(formData.latitude) : (userLocation?.lat ?? 17.97),
                              lng: formData.longitude ? parseFloat(formData.longitude) : (userLocation?.lng ?? 102.63)
                            }}
                            onLocationSelect={(location) => {
                              setFormData((prev) => ({
                                ...prev,
                                latitude: location.lat.toString(),
                                longitude: location.lng.toString(),
                                ...(typeof location.address === 'string' &&
                                location.address.length > 0 &&
                                !location.address.startsWith('ตำแหน่ง:')
                                  ? { address: location.address }
                                  : {}),
                              }));
                            }}
                            height="280px"
                            zoom={formData.latitude ? 17 : 12}
                          />
                          <p className="mt-2 text-xs text-secondary-500">
                            <FaMapMarkerAlt className="mr-1 inline h-3 w-3 text-secondary-500" aria-hidden />
                            {translate('entertainment.map_hint') === 'entertainment.map_hint'
                              ? 'Drag the map to adjust coordinates — search for a place using the address field above'
                              : translate('entertainment.map_hint')}
                          </p>
                        </>
                      ) : (
                        <div className="rounded-lg border border-dashed border-secondary-300 bg-secondary-50 px-4 py-3 text-sm text-secondary-600">
                          <p>
                            {translate('entertainment.map_collapsed_hint') ||
                              'Map hidden for easier scrolling — search for a place in the address field above. Click «Show Map» to adjust coordinates on the map.'}
                          </p>
                          {formData.latitude && formData.longitude ? (
                            <p className="mt-2 font-mono text-xs text-secondary-700">
                              {Number(formData.latitude).toFixed(6)}, {Number(formData.longitude).toFixed(6)}
                            </p>
                          ) : (
                            <p className="mt-2 text-xs text-secondary-500">
                              {translate('entertainment.no_coordinates_yet') || 'No coordinates set yet'}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.phone_label') || 'เบอร์โทร'}
                      </label>
                      <input
                        type="text"
                        value={formData.phone_number}
                        onChange={(e) =>
                          setFormData({ ...formData, phone_number: e.target.value })
                        }
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.opening_hours_label') || 'เวลาเปิด-ปิด'}
                      </label>
                      <input
                        type="text"
                        value={formData.opening_hours}
                        onChange={(e) =>
                          setFormData({ ...formData, opening_hours: e.target.value })
                        }
                        placeholder={translate('entertainment.opening_hours_placeholder') || 'เช่น 10:00 - 22:00'}
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.status_label') || 'สถานะ'}
                      </label>
                      <select
                        value={formData.status}
                        onChange={(e) =>
                          setFormData({ ...formData, status: e.target.value })
                        }
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
                      >
                        <option value="open">{translate('common.open') || 'เปิด'}</option>
                        <option value="closed">{translate('common.closed') || 'ปิด'}</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-secondary-700 mb-1">
                        {translate('entertainment.image') || 'รูปภาพ'}
                      </label>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={(e) =>
                          setFormData({ ...formData, image: e.target.files[0] })
                        }
                        className="w-full px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80"
                      />
                    </div>
                  </div>
                </form>
              )}
            </div>

            {modalType !== 'view' && (
              <div className="flex flex-col sm:flex-row justify-end gap-2 sm:gap-3 p-4 sm:p-6 border-t sticky bottom-0 bg-white">
                <button
                  onClick={() => setShowModal(false)}
                  className="w-full sm:w-auto px-4 py-2 border border-secondary-300 rounded-lg text-secondary-700 hover:bg-secondary-50"
                >
                  {translate('common.cancel') || 'ยกเลิก'}
                </button>
                <button
                  onClick={handleSave}
                  className="w-full rounded-lg bg-secondary-800 px-4 py-2 text-white hover:bg-secondary-900 sm:w-auto"
                >
                  {translate('common.save') || 'บันทึก'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Gallery Management Modal */}
      {showGalleryModal && selectedVenue && (
        <div className="fixed inset-0 z-[1200] flex items-start justify-center overflow-y-auto bg-black/50 p-2 pt-20 pb-8 sm:p-4 sm:pt-24">
          <div className="relative z-[1210] my-auto w-full max-w-6xl rounded-lg bg-white shadow-xl max-h-[min(90vh,calc(100vh-5rem))] overflow-y-auto">
            <div className="sticky top-0 z-10 flex flex-col gap-2 border-b bg-white p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-0 sm:p-6">
              <div className="flex-1 min-w-0">
                <h2 className="text-lg sm:text-xl md:text-2xl font-bold text-secondary-800 truncate">
                  <FcGallery className="inline mr-3 h-8 w-8 align-middle" aria-hidden /> <span className="text-xl sm:text-2xl md:text-2xl font-bold">{translate('entertainment.gallery_modal_title') || 'จัดการรูปภาพ'}</span>
                </h2>
                <p className="text-xs sm:text-sm text-secondary-500 mt-1 truncate">
                  {selectedVenue.venue_name}
                </p>
                <p className="text-xs sm:text-sm text-secondary-500 mt-1 hidden sm:block">
                  {translate('entertainment.manage_images') || 'อัปโหลด, จัดการ และเรียงลำดับรูปภาพ'}
                </p>
              </div>
              <button
                type="button"
                onClick={closeGalleryModal}
                className="text-secondary-400 hover:text-secondary-600 flex-shrink-0 self-end sm:self-auto"
              >
                <FaTimes className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden />
              </button>
            </div>

            <div className="p-4 sm:p-6">
              {/* Upload Section */}
              <div className="mb-4 sm:mb-6 p-3 sm:p-4 bg-secondary-50 rounded-lg">
                <label className="block text-sm font-medium text-secondary-700 mb-2">
                  <FaUpload className="inline mr-2" />
                  {translate('entertainment.upload_image') || 'อัปโหลดรูปภาพใหม่'}
                </label>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  disabled={gallerySaving}
                  onChange={handleAddGalleryFiles}
                  className="w-full text-xs sm:text-sm px-3 sm:px-4 py-2 border border-secondary-300 rounded-lg focus:border-secondary-400 focus:outline-none focus:ring-2 focus:ring-secondary-300/80 disabled:opacity-50"
                />
                <p className="text-xs text-secondary-500 mt-1">
                  {translate('common.supports_files') || 'สามารถเลือกหลายรูปได้ (รองรับ JPG, PNG, GIF)'}
                </p>
                <p className="text-xs text-amber-800/90 mt-2 rounded-md bg-amber-50 px-2 py-1.5 border border-amber-200/80">
                  {translate('entertainment.gallery_save_to_upload_hint') ||
                    'รูปที่เลือกจะยังไม่อัปโหลดจนกว่าจะกด «บันทึก» — ยกเลิกหรือปิดโมดัลจะละทิ้งรูปที่ยังไม่บันทึก'}
                </p>
              </div>

              {/* Images Grid */}
              {galleryDraft.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
                  {galleryDraft
                    .sort((a, b) => a.sort_order - b.sort_order)
                    .map((image, index) => (
                      <div
                        key={image._key}
                        className="relative group bg-secondary-100 rounded-lg overflow-hidden"
                      >
                        <div className="aspect-square">
                          <img
                            src={
                              image.previewUrl ||
                              image.image_display_url ||
                              image.image_url ||
                              image.image
                            }
                            alt={image.caption || `Image ${index + 1}`}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <div className="absolute top-2 left-2 max-w-[calc(100%-3rem)] bg-black bg-opacity-60 text-white text-xs px-2 py-1 rounded">
                          <span>#{image.sort_order}</span>
                          {image.file ? (
                            <span className="ml-1.5 text-amber-200">
                              · {translate('entertainment.gallery_pending_badge') || 'รอบันทึก'}
                            </span>
                          ) : null}
                        </div>
                        <div className="absolute top-1 right-1 sm:top-2 sm:right-2 flex flex-col space-y-0.5 sm:space-y-1">
                          <button
                            type="button"
                            onClick={() => handleMoveGalleryItem(image._key, 'up')}
                            disabled={index === 0 || gallerySaving}
                            className={`rounded p-0.5 sm:p-1 ${
                              index === 0
                                ? 'cursor-not-allowed bg-secondary-200 text-secondary-500 opacity-70'
                                : 'bg-secondary-600 text-white hover:bg-secondary-700'
                            }`}
                            title={translate('common.move_up') || 'ย้ายขึ้น'}
                          >
                            <FaArrowUp className="h-3 w-3 sm:h-4 sm:w-4" aria-hidden />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleMoveGalleryItem(image._key, 'down')}
                            disabled={index === galleryDraft.length - 1 || gallerySaving}
                            className={`rounded p-0.5 sm:p-1 ${
                              index === galleryDraft.length - 1
                                ? 'cursor-not-allowed bg-secondary-300 opacity-50'
                                : 'bg-secondary-600 text-white hover:bg-secondary-700'
                            } text-white`}
                            title={translate('common.move_down') || 'ย้ายลง'}
                          >
                            <FaArrowDown className="h-3 w-3 sm:h-4 sm:w-4" aria-hidden />
                          </button>
                        </div>
                        <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-60 p-1.5 sm:p-2">
                          <input
                            type="text"
                            value={image.caption || ''}
                            onChange={(e) =>
                              handleUpdateGalleryCaption(image._key, e.target.value)
                            }
                            disabled={gallerySaving}
                            placeholder={translate('entertainment.image_caption') || 'เพิ่มคำอธิบาย...'}
                            className="w-full px-1.5 sm:px-2 py-0.5 sm:py-1 text-xs text-white bg-transparent border border-white border-opacity-30 rounded focus:outline-none focus:border-white placeholder-white placeholder-opacity-50 disabled:opacity-50"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => handleDeleteGalleryItem(image._key)}
                          disabled={gallerySaving}
                          className="absolute left-1 top-1 rounded p-1 text-white opacity-0 transition-opacity group-hover:opacity-100 sm:left-2 sm:top-2 sm:p-1.5 bg-secondary-800 hover:bg-secondary-900 disabled:opacity-40"
                          title={translate('entertainment.delete_image') || 'ลบรูป'}
                        >
                          <FaTrash className="h-3 w-3 sm:h-4 sm:w-4" aria-hidden />
                        </button>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <FaImage className="w-16 h-16 text-secondary-300 mx-auto mb-4" />
                  <p className="text-secondary-500">{translate('entertainment.no_images') || 'ยังไม่มีรูปภาพ'}</p>
                  <p className="text-sm text-secondary-400 mt-2">
                    {translate('entertainment.upload_image') || 'อัปโหลดรูปภาพเพื่อเริ่มต้น'}
                  </p>
                </div>
              )}
            </div>

            <div className="flex flex-col sm:flex-row justify-end gap-2 sm:gap-3 p-4 sm:p-6 border-t sticky bottom-0 bg-white">
              <button
                type="button"
                onClick={closeGalleryModal}
                disabled={gallerySaving}
                className="w-full sm:w-auto px-4 py-2 border border-secondary-300 rounded-lg text-secondary-700 hover:bg-secondary-50 disabled:opacity-50"
              >
                {translate('common.cancel') || 'ยกเลิก'}
              </button>
              <button
                type="button"
                onClick={handleSaveGallery}
                disabled={gallerySaving}
                className="w-full rounded-lg bg-secondary-800 px-4 py-2 text-white hover:bg-secondary-900 sm:w-auto disabled:opacity-50"
              >
                {gallerySaving
                  ? translate('common.saving') || 'กำลังบันทึก...'
                  : translate('entertainment.save_gallery') || 'บันทึก'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Import Excel Modal ─────────────────────────────────────────────── */}
      {showImportModal && (
        <div className="fixed inset-0 z-[1200] flex items-start justify-center overflow-y-auto bg-black/50 p-2 pt-16 pb-8 sm:p-4 sm:pt-20">
          <div className="relative z-[1210] my-auto w-full max-w-5xl rounded-xl bg-white shadow-2xl">

            {/* Header */}
            <div className="flex items-center justify-between border-b px-6 py-4">
              <div className="flex items-center gap-3">
                <FaFileExcel className="h-6 w-6 text-green-600" aria-hidden />
                <div>
                  <h2 className="text-lg font-bold text-secondary-800">
                    {translate('entertainment.import_excel') || 'นำเข้า Excel'}
                  </h2>
                  <p className="text-xs text-secondary-500">
                    {translate('entertainment.import_excel_sub') || 'นำเข้าสถานที่หลายรายการพร้อมกันจากไฟล์ .xlsx'}
                  </p>
                </div>
              </div>
              <button type="button" onClick={resetImportModal}
                className="rounded-lg p-1.5 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600">
                <FaTimes className="h-5 w-5" aria-hidden />
              </button>
            </div>

            <div className="p-5 sm:p-6 space-y-6">

              {/* Step 1 — เลือกไฟล์ */}
              {(importStep === 'idle' || importStep === 'preview' || importStep === 'importing') && (
                <div className="rounded-xl border border-dashed border-secondary-300 bg-secondary-50 p-5">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-secondary-700">
                      1. {translate('entertainment.import_step_select') || 'เลือกไฟล์ Excel (.xlsx)'}
                    </p>
                  </div>
                  <input
                    ref={importFileRef}
                    type="file"
                    accept=".xlsx,.xls"
                    disabled={importStep === 'importing'}
                    onChange={handleImportFileChange}
                    className="w-full rounded-lg border border-secondary-300 bg-white px-3 py-2 text-sm focus:outline-none disabled:opacity-50"
                  />
                  <p className="mt-2 text-xs text-secondary-400">
                    {translate('entertainment.import_file_hint') ||
                      'Column ที่ต้องการ: venue_name, country_name, city_name, address, latitude, longitude, phone_number, opening_hours, description, status, category'}
                  </p>
                </div>
              )}

              {/* Step 2 — Preview ตาราง */}
              {(importStep === 'preview' || importStep === 'importing') && importRows.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-semibold text-secondary-700">
                    2. {translate('entertainment.import_step_preview') || 'ตรวจสอบข้อมูลก่อนนำเข้า'}
                    <span className="ml-2 rounded-full bg-secondary-100 px-2 py-0.5 text-xs text-secondary-600">
                      {importRows.length} รายการ
                    </span>
                  </p>
                  {importDuplicateNames.size > 0 && (
                    <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      <FaExclamationTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-500" />
                      <span>
                        {(translate('entertainment.import_duplicate_warning') || 'พบชื่อสถานที่ซ้ำกันในไฟล์ {n} ชื่อ — รายการที่ซ้ำกับฐานข้อมูลจะถูกข้าม').replace('{n}', importDuplicateNames.size)}
                      </span>
                    </div>
                  )}
                  <div className="overflow-x-auto rounded-lg border border-secondary-200">
                    <table className="min-w-full divide-y divide-secondary-200 text-xs">
                      <thead className="bg-secondary-50 text-secondary-600">
                        <tr>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">#</th>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">{translate('entertainment.venue_name_header') || 'ชื่อสถานที่'}</th>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">{translate('common.country') || 'ประเทศ'}</th>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">{translate('common.city') || 'เมือง'}</th>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">{translate('entertainment.address_label') || 'ที่อยู่'}</th>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">Lat</th>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">Lng</th>
                          <th className="whitespace-nowrap px-3 py-2 text-left font-semibold">{translate('entertainment.status_header') || 'สถานะ'}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-secondary-100 bg-white">
                        {importRows.slice(0, 50).map((row) => {
                          const isDup = importDuplicateNames.has(row.venue_name.toLowerCase());
                          return (
                          <tr key={row._row} className={isDup ? 'bg-amber-50' : 'hover:bg-secondary-50'}>
                            <td className="px-3 py-1.5 text-secondary-400">{row._row}</td>
                            <td className="max-w-[160px] px-3 py-1.5 font-medium text-secondary-800">
                              <div className="flex items-center gap-1">
                                <span className="truncate">{row.venue_name || <span className="text-red-400">{translate('entertainment.import_empty_field') || 'ว่าง!'}</span>}</span>
                                {isDup && <FaExclamationTriangle className="h-3 w-3 flex-shrink-0 text-amber-500" title={translate('entertainment.import_dup_in_file') || 'ชื่อซ้ำในไฟล์'} />}
                              </div>
                            </td>
                            <td className="px-3 py-1.5 text-secondary-600">{row.country_name || '—'}</td>
                            <td className="px-3 py-1.5 text-secondary-600">{row.city_name || '—'}</td>
                            <td className="max-w-[160px] truncate px-3 py-1.5 text-secondary-600">{row.address || '—'}</td>
                            <td className="px-3 py-1.5 font-mono text-secondary-500">{row.latitude || '—'}</td>
                            <td className="px-3 py-1.5 font-mono text-secondary-500">{row.longitude || '—'}</td>
                            <td className="px-3 py-1.5">
                              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                row.status === 'closed'
                                  ? 'bg-red-100 text-red-700'
                                  : 'bg-green-100 text-green-700'
                              }`}>
                                {row.status === 'closed' ? translate('common.closed') || 'ปิด' : translate('common.open') || 'เปิด'}
                              </span>
                            </td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {importRows.length > 50 && (
                      <p className="border-t bg-secondary-50 px-4 py-2 text-center text-xs text-secondary-400">
                        {(translate('entertainment.import_preview_limit') || 'แสดง 50 แถวแรก จากทั้งหมด {count} แถว').replace('{count}', importRows.length)}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Step 3 — กำลังนำเข้า */}
              {importStep === 'importing' && (
                <div className="flex items-center justify-center gap-3 rounded-lg bg-blue-50 px-4 py-4 text-blue-700">
                  <FaSpinner className="h-5 w-5 animate-spin" />
                  <span className="text-sm font-medium">
                    {translate('entertainment.import_in_progress') || `กำลังนำเข้า ${importRows.length} รายการ...`}
                  </span>
                </div>
              )}

              {/* Step 4 — ผลลัพธ์ */}
              {importStep === 'done' && importResult && (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-3">
                    <div className="flex items-center gap-3 rounded-xl border border-green-200 bg-green-50 px-4 py-4">
                      <FaCheckCircle className="h-7 w-7 flex-shrink-0 text-green-500" />
                      <div>
                        <p className="text-2xl font-bold text-green-700">{importResult.success ?? 0}</p>
                        <p className="text-xs text-green-600">
                          {translate('entertainment.import_success_count') || 'นำเข้าสำเร็จ'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-4">
                      <FaExclamationTriangle className="h-7 w-7 flex-shrink-0 text-amber-400" />
                      <div>
                        <p className="text-2xl font-bold text-amber-600">{importResult.duplicates ?? 0}</p>
                        <p className="text-xs text-amber-600">{translate('entertainment.import_skip_label') || 'ข้ามซ้ำ'}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4">
                      <FaExclamationTriangle className="h-7 w-7 flex-shrink-0 text-red-400" />
                      <div>
                        <p className="text-2xl font-bold text-red-600">{importResult.failed ?? 0}</p>
                        <p className="text-xs text-red-500">
                          {translate('entertainment.import_failed_count') || 'ล้มเหลว'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {importResult.duplicate_list && importResult.duplicate_list.length > 0 && (
                    <div>
                      <p className="mb-2 text-sm font-semibold text-amber-700">{translate('entertainment.import_duplicate_section') || 'รายการที่ถูกข้าม (ชื่อซ้ำในฐานข้อมูล)'}</p>
                      <div className="max-h-36 overflow-y-auto rounded-lg border border-amber-100">
                        <table className="min-w-full text-xs">
                          <thead className="bg-amber-50 text-amber-700">
                            <tr>
                              <th className="px-3 py-2 text-left">{translate('common.row') || 'แถว'}</th>
                              <th className="px-3 py-2 text-left">{translate('entertainment.venue_name_label') || 'ชื่อสถานที่'}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-amber-50 bg-white">
                            {importResult.duplicate_list.map((d, i) => (
                              <tr key={i}>
                                <td className="px-3 py-1.5 text-secondary-500">{d.row}</td>
                                <td className="px-3 py-1.5 text-secondary-700">{d.venue_name}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {importResult.errors && importResult.errors.length > 0 && (
                    <div>
                      <p className="mb-2 text-sm font-semibold text-red-700">{translate('entertainment.import_error_section') || 'รายการที่มีปัญหา'}</p>
                      <div className="max-h-48 overflow-y-auto rounded-lg border border-red-100">
                        <table className="min-w-full text-xs">
                          <thead className="bg-red-50 text-red-700">
                            <tr>
                              <th className="px-3 py-2 text-left">{translate('common.row') || 'แถว'}</th>
                              <th className="px-3 py-2 text-left">{translate('entertainment.venue_name_label') || 'ชื่อ'}</th>
                              <th className="px-3 py-2 text-left">{translate('common.error') || 'ข้อผิดพลาด'}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-red-50 bg-white">
                            {importResult.errors.map((e, i) => (
                              <tr key={i}>
                                <td className="px-3 py-1.5 text-secondary-500">{e.row ?? '—'}</td>
                                <td className="max-w-[120px] truncate px-3 py-1.5 text-secondary-700">{e.venue_name ?? '—'}</td>
                                <td className="px-3 py-1.5 text-red-600">{e.message ?? JSON.stringify(e.errors ?? e)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {importResult.new_countries && importResult.new_countries.length > 0 && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                      <span className="font-semibold">{translate('entertainment.import_new_countries') || 'สร้างประเทศใหม่'}: </span>
                      {importResult.new_countries.join(', ')}
                    </div>
                  )}
                  {importResult.new_cities && importResult.new_cities.length > 0 && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                      <span className="font-semibold">{translate('entertainment.import_new_cities') || 'สร้างเมืองใหม่'}: </span>
                      {importResult.new_cities.join(', ')}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex flex-col-reverse gap-2 border-t px-6 py-4 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={resetImportModal}
                className="w-full rounded-lg border border-secondary-300 px-4 py-2 text-sm text-secondary-700 hover:bg-secondary-50 sm:w-auto"
              >
                {importStep === 'done' ? (translate('common.close') || 'ปิด') : (translate('common.cancel') || 'ยกเลิก')}
              </button>

              {importStep === 'preview' && importRows.length > 0 && (
                <button
                  type="button"
                  onClick={handleRunImport}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-green-600 px-5 py-2 text-sm font-semibold text-white hover:bg-green-700 sm:w-auto"
                >
                  <FaFileExcel className="h-4 w-4" />
                  {translate('entertainment.import_confirm') || `นำเข้า ${importRows.length} รายการ`}
                </button>
              )}

              {importStep === 'done' && (
                <button
                  type="button"
                  onClick={() => { setImportStep('idle'); setImportRows([]); setImportResult(null); }}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-green-500 px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-50 sm:w-auto"
                >
                  <FaFileExcel className="h-4 w-4" />
                  {translate('entertainment.import_again') || 'นำเข้าไฟล์ใหม่'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminEntertainmentVenues;
