import React from 'react';

const artwork = {
  cake: <path d="M4 20v-7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7M2 20h20M4 16c2 2 4 2 6 0 1 2 3 2 4 0 2 2 4 2 6 0M8 11V8m4 3V8m4 3V8M8 5v.1M12 4v.1M16 5v.1"/>,
  heart: <path d="M20.8 8.6c0 4.2-8.8 9.8-8.8 9.8s-8.8-5.6-8.8-9.8a4.5 4.5 0 0 1 8.8-1.3 4.5 4.5 0 0 1 8.8 1.3Z"/>,
  pin: <>
    <path d="M19 10c0 4.4-7 10-7 10s-7-5.6-7-10a7 7 0 1 1 14 0Z"/>
    <circle cx="12" cy="10" r="2.25"/>
  </>,
  cloud: <path d="M7 18a4 4 0 1 1 .7-7.9 5 5 0 0 1 9.7 1.1 3.4 3.4 0 1 1 .3 6.8H7Z"/>,
  smile: <>
    <circle cx="12" cy="12" r="8.5"/>
    <path d="M8.5 14a4 4 0 0 0 7 0M9 10v.1m6-.1v.1"/>
  </>,
};

export function Icon({name}) {
  return <svg className={`ui-icon ui-icon--${name}`} viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth={1.5}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {artwork[name]}
  </svg>;
}
