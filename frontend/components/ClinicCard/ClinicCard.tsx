'use client';

import React, { memo } from 'react';
import Link from 'next/link';
import { User, MapPin, Phone, ArrowUpRight } from 'lucide-react';
import styles from './ClinicCard.module.css';

interface Provider {
  id: string;
  name: string;
  specialty: string;
  bio: string;
  city: string;
  address: string;
  phone: string;
}

interface ClinicCardProps {
  provider: Provider;
  canCall?: boolean;
  onCallClick?: (id: string) => void;
}

function ClinicCardBase({ provider, canCall: canCallProp, onCallClick }: ClinicCardProps) {
  // If canCall is not provided, we check if the provider has a phone number
  const isAvailable = canCallProp !== undefined ? canCallProp : !!provider.phone;

  return (
    <div className={styles.card}>
      {/* Top row: avatar + status */}
      <div className={styles.cardTop}>
        <div className={styles.avatar}>
          <User size={24} />
        </div>
        <div className={styles.statusPill} data-available={isAvailable}>
          <span className={styles.statusDot}>
            <span className={isAvailable ? styles.statusDotPing : styles.statusDotOffline} />
            <span className={isAvailable ? styles.statusDotCore : styles.statusDotCoreOffline} />
          </span>
          <span className={styles.statusText}>
            {isAvailable ? 'Available' : 'Unavailable'}
          </span>
        </div>
      </div>

      {/* Doctor info */}
      <div>
        <h3 className={styles.doctorName}>{provider.name}</h3>
        <p className={styles.specialty}>{provider.specialty}</p>
      </div>

      {/* Bio */}
      <p className={styles.bio}>{provider.bio}</p>

      {/* Location */}
      <div className={styles.locationRow}>
        <MapPin size={13} className={styles.locationIcon} />
        <span>{provider.city} &bull; {provider.address}</span>
      </div>

      {/* Action buttons */}
      <div className={styles.buttons}>
        <button
          type="button"
          className={`${styles.btnCall} ${!isAvailable ? styles.btnCallDisabled : ''}`}
          onClick={() => {
            if (!isAvailable) return;
            onCallClick?.(provider.id);
          }}
          disabled={!isAvailable}
          aria-label={isAvailable ? `Call ${provider.name}'s clinic` : 'No phone number available'}
          title={isAvailable ? undefined : 'No registered phone number for this clinic'}
        >
          <Phone size={13} />
          {isAvailable ? 'Direct Call' : 'Unavailable'}
        </button>
        <Link
          href={`/book?providerId=${provider.id}`}
          className={styles.btnBook}
          aria-label={`Book appointment with ${provider.name}`}
        >
          Book Appointment
          <ArrowUpRight size={13} className={styles.btnBookArrow} />
        </Link>
      </div>
    </div>
  );
}

export const ClinicCard = memo(ClinicCardBase);
