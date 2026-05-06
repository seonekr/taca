import React, { useState, useRef, useEffect } from 'react';
import { FaSearch } from 'react-icons/fa';
import { useLanguage } from '../../contexts/LanguageContext';
import { searchAddresses, geocodeAddress } from '../../utils/nominatim';

// Open Location Code (Plus Code) constants
const OLC_ALPHABET = '23456789CFGHJMPQRVWX';
const PAIR_RESOLUTIONS = [20.0, 1.0, 0.05, 0.0025, 0.000125];
const SEPARATOR_POSITION = 8;

const PLUS_CODE_RE = /^[23456789CFGHJMPQRVWXcfghjmpqrvwx]{2,8}\+[23456789CFGHJMPQRVWXcfghjmpqrvwx]{2,7}$/;
const COORD_RE = /^(-?\d{1,3}\.?\d*)[,\s]+(-?\d{1,3}\.?\d*)$/;

function parseCoordinates(input) {
  const match = input.trim().match(COORD_RE);
  if (!match) return null;
  const lat = parseFloat(match[1]);
  const lng = parseFloat(match[2]);
  if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) return { lat, lng };
  return null;
}

function encodePlusCodePrefix(lat, lng, prefixLen) {
  let latNorm = Math.min(lat + 90, 180 - 1e-10);
  let lngNorm = ((lng + 180) % 360 + 360) % 360;
  lngNorm = Math.min(lngNorm, 360 - 1e-10);
  let code = '';
  for (let i = 0; i < prefixLen; i++) {
    const resolution = PAIR_RESOLUTIONS[Math.floor(i / 2)];
    if (i % 2 === 0) {
      const d = Math.floor(latNorm / resolution);
      code += OLC_ALPHABET[d];
      latNorm -= d * resolution;
    } else {
      const d = Math.floor(lngNorm / resolution);
      code += OLC_ALPHABET[d];
      lngNorm -= d * resolution;
    }
  }
  return code;
}

// Decode a full or short Plus Code to { lat, lng }
// For short codes, referenceLat/Lng is required
function decodePlusCode(code, referenceLat = null, referenceLng = null) {
  const upper = code.toUpperCase().trim();
  const sepIdx = upper.indexOf('+');
  if (sepIdx < 0 || upper.length - sepIdx < 3) return null;
  if (sepIdx > SEPARATOR_POSITION) return null;

  const withoutSep = upper.replace('+', '');
  for (const c of withoutSep) {
    if (!OLC_ALPHABET.includes(c)) return null;
  }

  let digits = withoutSep;
  if (sepIdx < SEPARATOR_POSITION) {
    if (referenceLat === null || referenceLng === null) return null;
    const missingLen = SEPARATOR_POSITION - sepIdx;
    const prefix = encodePlusCodePrefix(referenceLat, referenceLng, missingLen);
    digits = prefix + digits;
  }

  let lat = -90.0;
  let lng = -180.0;
  let latResolution = 20.0;
  let lngResolution = 20.0;

  for (let i = 0; i < Math.min(digits.length, 10); i++) {
    const resolution = PAIR_RESOLUTIONS[Math.floor(i / 2)];
    const digitVal = OLC_ALPHABET.indexOf(digits[i]);
    if (digitVal < 0) return null;
    if (i % 2 === 0) {
      latResolution = resolution;
      lat += resolution * digitVal;
    } else {
      lngResolution = resolution;
      lng += resolution * digitVal;
    }
  }

  return {
    lat: lat + latResolution / 2,
    lng: lng + lngResolution / 2,
  };
}

/**
 * AddressPickerLeaflet Component
 * Component สำหรับเลือกที่อยู่โดยใช้ Nominatim Autocomplete (OpenStreetMap)
 * รองรับ: ชื่อสถานที่, ที่อยู่, พิกัด (lat, lng), Plus Code (เต็ม/ย่อ)
 */
const AddressPickerLeaflet = ({
  value = '',
  onChange,
  onLocationSelect,
  placeholder,
  className = '',
  required = false,
  readOnly = false,
  referenceLocation = null,
}) => {
  const { translate } = useLanguage();
  const [address, setAddress] = useState(value);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef(null);
  const suggestionsRef = useRef(null);
  const debounceTimerRef = useRef(null);

  useEffect(() => {
    setAddress(value);
  }, [value]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        suggestionsRef.current &&
        !suggestionsRef.current.contains(event.target) &&
        inputRef.current &&
        !inputRef.current.contains(event.target)
      ) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleInputChange = (e) => {
    if (readOnly) return;
    const newValue = e.target.value;
    setAddress(newValue);
    setError(null);
    setSelectedIndex(-1);
    if (onChange) onChange(newValue);

    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);

    const trimmed = newValue.trim();

    // 1. Detect lat,lng coordinates
    const coords = parseCoordinates(trimmed);
    if (coords) {
      setSuggestions([]);
      setShowSuggestions(false);
      if (onLocationSelect) onLocationSelect({ ...coords, address: trimmed });
      return;
    }

    // 2. Detect Plus Code (full or short)
    if (PLUS_CODE_RE.test(trimmed.toUpperCase())) {
      setSuggestions([]);
      setShowSuggestions(false);
      const ref = referenceLocation;
      const decoded = decodePlusCode(trimmed, ref?.lat ?? null, ref?.lng ?? null);
      if (decoded) {
        setError(null);
        if (onLocationSelect) onLocationSelect({ ...decoded, address: trimmed });
      } else if (!ref) {
        setError(translate('address_picker.error_short_plus_code') || 'Short Plus Code requires a reference location — try selecting an area on the map first, or add a city name, e.g. "XH9W+QR Vientiane"');
      } else {
        setError(translate('address_picker.error_decode_failed') || 'Unable to decode this Plus Code');
      }
      return;
    }

    // 3. Regular Nominatim autocomplete
    if (trimmed.length >= 3) {
      debounceTimerRef.current = setTimeout(async () => {
        setIsLoading(true);
        try {
          const results = await searchAddresses(trimmed);
          setSuggestions(results);
          setShowSuggestions(results.length > 0);
          if (results.length === 0) {
            setError(null);
          }
        } catch (err) {
          console.error('Search error:', err);
          setSuggestions([]);
        } finally {
          setIsLoading(false);
        }
      }, 400);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  };

  const handleSelectSuggestion = (suggestion) => {
    setAddress(suggestion.address);
    setShowSuggestions(false);
    setSuggestions([]);
    setError(null);
    if (onChange) onChange(suggestion.address);
    if (onLocationSelect) {
      onLocationSelect({
        lat: suggestion.lat,
        lng: suggestion.lng,
        address: suggestion.address,
        place_id: suggestion.place_id,
      });
    }
  };

  // Search on Enter (when no suggestion highlighted)
  const handleManualGeocode = async () => {
    const query = address.trim();
    if (!query) return;
    setError(null);
    setSuggestions([]);
    setShowSuggestions(false);

    // Handle coordinates directly (no network needed)
    const coords = parseCoordinates(query);
    if (coords) {
      if (onLocationSelect) onLocationSelect({ ...coords, address: query });
      return;
    }

    // Handle Plus Code directly (no network needed)
    if (PLUS_CODE_RE.test(query.toUpperCase())) {
      const ref = referenceLocation;
      const decoded = decodePlusCode(query, ref?.lat ?? null, ref?.lng ?? null);
      if (decoded) {
        if (onChange) onChange(query);
        if (onLocationSelect) onLocationSelect({ ...decoded, address: query });
      } else if (!ref) {
        setError(translate('address_picker.error_short_plus_code') || 'Short Plus Code requires a reference location');
      } else {
        setError(translate('address_picker.error_decode_failed') || 'Unable to decode this Plus Code');
      }
      return;
    }

    setIsLoading(true);

    const commitResult = (result) => {
      setAddress(result.address);
      if (onChange) onChange(result.address);
      if (onLocationSelect) {
        onLocationSelect({
          lat: result.lat,
          lng: result.lng,
          address: result.address,
          place_id: result.place_id,
        });
      }
    };

    // Build progressively simpler fallback queries for when Nominatim
    // doesn't have the full structured address (common for Laos/SE-Asia).
    // e.g. "Nongduang Nua Village, 20 Rue Samsenthai, Vientiane 01000"
    //   → "20 Rue Samsenthai, Vientiane 01000"
    //   → "Rue Samsenthai, Vientiane 01000"
    //   → "Vientiane"
    const parts = query.split(',').map((p) => p.trim()).filter(Boolean);
    const queriesToTry = [query];
    if (parts.length >= 2) {
      queriesToTry.push(parts.slice(1).join(', '));
    }
    if (parts.length >= 3) {
      const streetNoNum = parts[1].replace(/^\d+\s+/, '');
      if (streetNoNum !== parts[1]) {
        queriesToTry.push([streetNoNum, ...parts.slice(2)].join(', '));
      }
    }
    if (parts.length >= 2) {
      const cityPart = parts[parts.length - 1].replace(/\s*\d{4,6}$/, '').trim();
      if (cityPart) queriesToTry.push(cityPart);
    }

    try {
      for (const q of queriesToTry) {
        try {
          const result = await geocodeAddress(q);
          commitResult(result);
          return;
        } catch {
          // try next simplified query
        }
      }
      setError(translate('address_picker.error_not_found') || 'Location not found. Try a shorter name, e.g. "Rue Samsenthai, Vientiane"');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (showSuggestions && selectedIndex >= 0 && suggestions.length > 0) {
        handleSelectSuggestion(suggestions[selectedIndex]);
      } else if (!showSuggestions || suggestions.length === 0) {
        handleManualGeocode();
      }
      return;
    }
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : -1));
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  return (
    <div className={`address-picker-leaflet relative ${className}`}>
      {readOnly ? (
        <div className="w-full px-4 py-2 border border-secondary-300 rounded-lg bg-secondary-50 text-secondary-700">
          {address || placeholder}
        </div>
      ) : (
        <div className="relative flex gap-2">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              type="text"
              value={address}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              onFocus={() => {
                if (suggestions.length > 0) setShowSuggestions(true);
              }}
              placeholder={placeholder ?? translate('entertainment.address_search_placeholder') ?? 'Type place name, address, coordinates or Plus Code'}
              className={`w-full px-4 py-2 border border-secondary-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                error ? 'border-red-500' : ''
              }`}
              required={required}
            />
            {isLoading && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary-500" />
              </div>
            )}

            {showSuggestions && suggestions.length > 0 && (
              <div
                ref={suggestionsRef}
                className="absolute left-0 right-0 top-full mt-1 bg-white border border-secondary-300 rounded-lg shadow-lg max-h-60 overflow-y-auto z-[9999]"
              >
                {suggestions.map((suggestion, index) => (
                  <button
                    key={suggestion.place_id || index}
                    type="button"
                    onClick={() => handleSelectSuggestion(suggestion)}
                    className={`w-full text-left px-4 py-2 hover:bg-primary-50 ${
                      index === selectedIndex ? 'bg-primary-100' : ''
                    } ${index !== suggestions.length - 1 ? 'border-b border-secondary-200' : ''}`}
                  >
                    <div className="text-sm text-secondary-800">{suggestion.address}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Search button — trigger geocoding on demand */}
          <button
            type="button"
            onClick={handleManualGeocode}
            disabled={isLoading || !address.trim()}
            className="shrink-0 px-3 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed text-sm"
            title={translate('address_picker.search_title') || 'Search (Enter)'}
          >
            <FaSearch className="h-4 w-4" aria-hidden />
          </button>
        </div>
      )}

      {error && (
        <p className="mt-1 text-sm text-red-600">{error}</p>
      )}

      {!error && (
        <p className="mt-1 text-xs text-secondary-400">
          {translate('address_picker.hint') || 'Supports: place name · address · coordinates (17.97, 102.63) · Plus Code (XH9W+QR) — press Enter or click search'}
        </p>
      )}
    </div>
  );
};

export default AddressPickerLeaflet;
