// utils/index.tsx

import { openDB, DBSchema } from 'idb';

// --- Re-export the document utils as before ---
export { groupLinksByType, LinksByType, getDocumentDisplayName } from './document';


// --- NEW: IndexedDB Setup and Helpers ---

const DB_NAME = 'DataCacheDB';
const STORE_NAME = 'KeyValStore';
const DB_VERSION = 1;

// Define the database schema for type safety
interface CacheDB extends DBSchema {
  [STORE_NAME]: {
    key: string;
    value: {
      value: any; // The actual data
      expiry: number; // The expiry timestamp
    };
  };
}

// Initialize the database connection promise
const dbPromise = openDB<CacheDB>(DB_NAME, DB_VERSION, {
  upgrade(db) {
    // This store will hold key-value pairs, just like localStorage
    db.createObjectStore(STORE_NAME);
  },
});

/**
 * Retrieves an item from IndexedDB and checks if it's expired.
 * Returns the value if found and valid, otherwise returns null.
 */
export const getDbObject = async (key: string): Promise<any | null> => {
  const db = await dbPromise;
  const item = await db.get(STORE_NAME, key);

  if (!item) {
    return null; // Not found
  }

  // Check expiry
  if (Date.now() > item.expiry) {
    // Cache expired, delete it async (don't need to wait for it to finish)
    db.delete(STORE_NAME, key);
    return null;
  }

  return item.value;
};

/**
 * Stores an item in IndexedDB with an expiry timestamp.
 */
export const setDbObject = async (key: string, value: any, ttl: number): Promise<void> => {
  const db = await dbPromise;
  const expiry = Date.now() + ttl;
  const item = {
    value,
    expiry,
  };
  await db.put(STORE_NAME, item, key);
};