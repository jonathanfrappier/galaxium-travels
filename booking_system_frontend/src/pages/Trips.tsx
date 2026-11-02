import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Search, Compass, AlertCircle, Sparkles, CheckCircle2 } from 'lucide-react';
import toast from 'react-hot-toast';
import type { ItinerarySearchResult, Itinerary, ErrorResponse } from '../types';
import { Button, LoadingSpinner, Input } from '../components/common';
import { TripTimeline } from '../components/trips/TripTimeline';
import { UserIdentification } from '../components/user/UserIdentification';
import { searchItineraries, createItinerary, confirmItinerary, getUserItineraries } from '../services/api';
import { useUser } from '../hooks/useUserContext';

export const Trips: React.FC = () => {
  const { user } = useUser();

  // Search form state
  const [origin, setOrigin] = useState('Earth');
  const [destination, setDestination] = useState('Europa');
  const [date, setDate] = useState('2099-02-01');

  // Search results state
  const [hasSearched, setHasSearched] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<ItinerarySearchResult[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Booking state
  const [bookingIndex, setBookingIndex] = useState<number | null>(null);
  const [pendingRoute, setPendingRoute] = useState<ItinerarySearchResult | null>(null);
  const [showUserModal, setShowUserModal] = useState(false);

  // My Trips state
  const [myTrips, setMyTrips] = useState<Itinerary[]>([]);
  const [isLoadingTrips, setIsLoadingTrips] = useState(false);

  const loadMyTrips = useCallback(async () => {
    if (!user) {
      setMyTrips([]);
      return;
    }
    setIsLoadingTrips(true);
    try {
      const trips = await getUserItineraries(user.user_id);
      setMyTrips(trips);
    } catch (err) {
      console.error('Failed to load user itineraries:', err);
    } finally {
      setIsLoadingTrips(false);
    }
  }, [user]);

  useEffect(() => {
    loadMyTrips();
  }, [loadMyTrips]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!origin.trim() || !destination.trim() || !date.trim()) {
      toast.error('Please enter origin, destination, and departure date.');
      return;
    }

    setIsSearching(true);
    setSearchError(null);
    setHasSearched(true);

    try {
      const results = await searchItineraries(origin.trim(), destination.trim(), date.trim());
      setSearchResults(results);
    } catch (err) {
      const error = err as ErrorResponse;
      const errorMsg = error.details || error.error || 'Failed to search for itineraries.';
      setSearchError(errorMsg);
      setSearchResults([]);
      toast.error(errorMsg);
    } finally {
      setIsSearching(false);
    }
  };

  const executeBooking = async (route: ItinerarySearchResult, currentUser: typeof user) => {
    if (!currentUser) return;

    try {
      // Step 1: Create held itinerary
      const flightIds = route.legs.map((leg) => leg.flight_id);
      const heldItinerary = await createItinerary({
        user_id: currentUser.user_id,
        name: currentUser.name,
        flight_ids: flightIds,
      });

      // Step 2: Confirm itinerary
      await confirmItinerary(heldItinerary.id);

      toast.success('Trip booked successfully!');
      setPendingRoute(null);
      await loadMyTrips();
    } catch (err) {
      const error = err as ErrorResponse;
      const errorMsg = error.details || error.error || 'Failed to book trip.';
      toast.error(errorMsg);
    } finally {
      setBookingIndex(null);
    }
  };

  const handleBookTrip = async (route: ItinerarySearchResult, index: number) => {
    setBookingIndex(index);
    if (!user) {
      setPendingRoute(route);
      setShowUserModal(true);
      return;
    }

    await executeBooking(route, user);
  };

  const handleUserIdentified = () => {
    setShowUserModal(false);
    if (pendingRoute && user) {
      executeBooking(pendingRoute, user);
    }
  };

  return (
    <div className="space-y-12 max-w-5xl mx-auto">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <h1 className="text-4xl md:text-5xl font-bold text-star-white mb-4">
          Multi-Leg <span className="bg-cosmic-gradient bg-clip-text text-transparent">Trips</span>
        </h1>
        <p className="text-star-white/70 text-lg">
          Connect up to 3 flights across the cosmos with seamless layovers in one click
        </p>
      </motion.div>

      {/* Search Form Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass-card p-6 md:p-8"
      >
        <form onSubmit={handleSearch} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-star-white/80 mb-1.5">
                Origin
              </label>
              <Input
                type="text"
                placeholder="e.g. Earth"
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-star-white/80 mb-1.5">
                Destination
              </label>
              <Input
                type="text"
                placeholder="e.g. Europa"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-star-white/80 mb-1.5">
                Departure Date
              </label>
              <Input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button
              type="submit"
              disabled={isSearching}
              className="flex items-center gap-2 px-6"
            >
              <Search size={18} />
              <span>{isSearching ? 'Searching Routes...' : 'Search Trips'}</span>
            </Button>
          </div>
        </form>
      </motion.div>

      {/* Search Results Section */}
      {isSearching && (
        <div className="py-12">
          <LoadingSpinner size="lg" text="Searching optimal orbital routes..." />
        </div>
      )}

      {!isSearching && searchError && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass-card p-6 text-center border-red-500/30 bg-red-500/10"
        >
          <AlertCircle className="mx-auto mb-2 text-red-400" size={32} />
          <p className="text-red-300 font-medium">{searchError}</p>
        </motion.div>
      )}

      {!isSearching && hasSearched && !searchError && searchResults.length === 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass-card p-12 text-center"
        >
          <Compass className="mx-auto mb-4 text-star-white/40" size={48} />
          <h3 className="text-xl font-semibold text-star-white mb-2">No routes found</h3>
          <p className="text-star-white/60 max-w-md mx-auto">
            No connecting flight routes found between {origin} and {destination} on {date}. Try another date or destinations.
          </p>
        </motion.div>
      )}

      {!isSearching && searchResults.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold text-star-white flex items-center gap-2">
              <Sparkles className="text-cosmic-purple" size={24} />
              Available Routes ({searchResults.length})
            </h2>
            <span className="text-xs text-star-white/60">
              Sorted by travel time and price
            </span>
          </div>

          <div className="space-y-6">
            {searchResults.map((route, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
                className="glass-card p-6 space-y-4"
              >
                <TripTimeline
                  legs={route.legs}
                  totalPrice={route.total_price}
                  totalDurationMinutes={route.total_duration_minutes}
                />
                <div className="flex justify-end pt-2">
                  <Button
                    onClick={() => handleBookTrip(route, idx)}
                    disabled={bookingIndex !== null}
                    className="flex items-center gap-2"
                  >
                    <CheckCircle2 size={18} />
                    <span>{bookingIndex === idx ? 'Booking Trip...' : 'Book Trip'}</span>
                  </Button>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* My Trips Section */}
      {user && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="space-y-6 pt-8 border-t border-white/10"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-3xl font-bold text-star-white">
              My <span className="bg-cosmic-gradient bg-clip-text text-transparent">Trips</span>
            </h2>
            <span className="text-sm text-star-white/60">
              {myTrips.length} {myTrips.length === 1 ? 'trip' : 'trips'} booked
            </span>
          </div>

          {isLoadingTrips ? (
            <LoadingSpinner size="md" text="Loading your trips..." />
          ) : myTrips.length === 0 ? (
            <div className="glass-card p-8 text-center">
              <Compass className="mx-auto mb-3 text-star-white/40" size={40} />
              <p className="text-star-white/70">No trips booked yet.</p>
              <p className="text-xs text-star-white/50 mt-1">
                Search above to find and book your next multi-leg journey!
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {myTrips.map((trip) => {
                const tripLegs = trip.legs.map((leg) => leg.flight).filter((f): f is NonNullable<typeof f> => Boolean(f));
                return (
                  <div key={trip.id} className="glass-card p-6">
                    <TripTimeline
                      legs={tripLegs}
                      totalPrice={trip.total_price}
                      status={trip.status}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </motion.div>
      )}

      {/* User Identification Modal */}
      <UserIdentification
        isOpen={showUserModal}
        onClose={() => {
          setShowUserModal(false);
          setBookingIndex(null);
        }}
        onSuccess={handleUserIdentified}
      />
    </div>
  );
};
