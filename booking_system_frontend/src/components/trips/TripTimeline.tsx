import React from 'react';
import { Plane, Clock, ArrowRight, ShieldCheck } from 'lucide-react';
import type { Flight } from '../../types';
import { formatCurrency, formatDate, formatTime, calculateDuration } from '../../utils/formatters';

interface TripTimelineProps {
  legs: Flight[];
  totalPrice?: number;
  totalDurationMinutes?: number;
  status?: string;
}

export const TripTimeline: React.FC<TripTimelineProps> = ({
  legs,
  totalPrice,
  totalDurationMinutes,
  status,
}) => {
  if (!legs || legs.length === 0) {
    return null;
  }

  const firstLeg = legs[0];
  const lastLeg = legs[legs.length - 1];

  const formattedTotalDuration = totalDurationMinutes
    ? `${Math.floor(totalDurationMinutes / 60)}h ${totalDurationMinutes % 60 > 0 ? `${totalDurationMinutes % 60}m` : ''}`.trim()
    : calculateDuration(firstLeg.departure_time, lastLeg.arrival_time);

  const calculatedTotalPrice = totalPrice ?? legs.reduce((acc, leg) => acc + (leg.base_price || 0), 0);

  return (
    <div className="bg-space-dark/60 border border-white/10 rounded-xl p-5 space-y-4">
      {/* Header Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/10">
        <div className="flex items-center gap-2 text-star-white font-bold text-lg">
          <span>{firstLeg.origin}</span>
          <ArrowRight className="text-cosmic-purple" size={18} />
          <span>{lastLeg.destination}</span>
          <span className="text-xs bg-space-blue/30 text-cosmic-purple px-2 py-0.5 rounded-full border border-cosmic-purple/30 font-normal">
            {legs.length} {legs.length === 1 ? 'leg' : 'legs'}
          </span>
        </div>

        <div className="flex items-center gap-4">
          {status && (
            <div className="flex items-center gap-1 text-xs text-alien-green bg-alien-green/10 border border-alien-green/30 px-2.5 py-1 rounded-full font-medium">
              <ShieldCheck size={14} />
              <span className="capitalize">{status}</span>
            </div>
          )}
          <div className="flex items-center gap-1 text-star-white/70 text-sm">
            <Clock size={16} />
            <span>{formattedTotalDuration}</span>
          </div>
          <div className="text-alien-green font-bold text-lg">
            {formatCurrency(calculatedTotalPrice)}
          </div>
        </div>
      </div>

      {/* Leg Timelines */}
      <div className="space-y-3">
        {legs.map((leg, index) => {
          const prevLeg = index > 0 ? legs[index - 1] : null;
          const layover = prevLeg ? calculateDuration(prevLeg.arrival_time, leg.departure_time) : null;

          return (
            <React.Fragment key={leg.flight_id || index}>
              {/* Layover Indicator */}
              {layover && (
                <div className="flex items-center gap-2 pl-4 py-1 text-xs text-solar-orange/90 font-medium">
                  <div className="w-2 h-2 rounded-full bg-solar-orange animate-pulse" />
                  <span>Layover in {prevLeg?.destination}: {layover}</span>
                </div>
              )}

              {/* Flight Leg Card */}
              <div className="bg-white/5 border border-white/10 rounded-lg p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-cosmic-purple/20 text-cosmic-purple">
                    <Plane size={18} />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-star-white">
                      Leg {index + 1}: {leg.origin} → {leg.destination}
                    </div>
                    <div className="text-xs text-star-white/60">
                      Flight #{leg.flight_id} • Economy Class
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-xs">
                  <div>
                    <span className="text-star-white/60 block">Departs</span>
                    <span className="font-medium text-star-white">
                      {formatDate(leg.departure_time, 'MMM dd, yyyy')} {formatTime(leg.departure_time)}
                    </span>
                  </div>
                  <div>
                    <span className="text-star-white/60 block">Arrives</span>
                    <span className="font-medium text-star-white">
                      {formatDate(leg.arrival_time, 'MMM dd, yyyy')} {formatTime(leg.arrival_time)}
                    </span>
                  </div>
                  <div className="col-span-2 md:col-span-1 text-right md:text-left">
                    <span className="text-star-white/60 block">Price</span>
                    <span className="font-semibold text-alien-green">
                      {formatCurrency(leg.base_price)}
                    </span>
                  </div>
                </div>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
