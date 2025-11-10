// components/NotificationsListener.tsx
'use client';

import * as React from "react";
import {
  collection,
  CollectionReference,
  deleteDoc,
  doc,
  DocumentData,
  Firestore,
  FirestoreDataConverter,
  getDocs,
  limit as qLimit,
  onSnapshot,
  orderBy,
  query,
  Query,
  QueryConstraint,
  Timestamp,
  Unsubscribe,
  updateDoc,
  where,
  writeBatch,
  serverTimestamp,
} from "firebase/firestore";

// ---------- Types ----------

export type NotificationKind =
  | "credit_threshold"
  | "badge_level"
  | "tier_up"
  | "like"
  | "remix"
  | "message"
  | string;

export type Notification = {
  id: string;
  kind: NotificationKind;
  title: string;
  body: string;
  data?: Record<string, unknown>;
  seen: boolean;
  ts?: Date;
  expiresAt?: Date;
};

type NotificationDoc = Omit<Notification, "id" | "ts" | "expiresAt"> & {
  ts?: Timestamp | Date;
  expiresAt?: Timestamp | Date;
};

// Converter
const notificationConverter: FirestoreDataConverter<Notification> = {
  toFirestore(n: Notification): DocumentData {
    return {
      kind: n.kind,
      title: n.title,
      body: n.body,
      data: n.data ?? {},
      seen: !!n.seen,
      ts: n.ts ? Timestamp.fromDate(n.ts) : serverTimestamp(),
      expiresAt: n.expiresAt ? Timestamp.fromDate(n.expiresAt) : undefined,
    };
  },
  fromFirestore(snapshot): Notification {
    const d = snapshot.data() as NotificationDoc;
    return {
      id: snapshot.id,
      kind: d.kind,
      title: d.title,
      body: d.body,
      data: d.data,
      seen: !!d.seen,
      ts:
        d.ts instanceof Timestamp
          ? d.ts.toDate()
          : d.ts instanceof Date
          ? d.ts
          : undefined,
      expiresAt:
        d.expiresAt instanceof Timestamp
          ? d.expiresAt.toDate()
          : d.expiresAt instanceof Date
          ? d.expiresAt
          : undefined,
    };
  },
};

// ---------- Identity lookup ----------

async function resolveIdentityDocIdByUserId(
  db: Firestore,
  userId: string
): Promise<string | null> {
  try {
    const q = query(
      collection(db, "identity"),
      where("userID", "==", userId),
      qLimit(1)
    );
    const snap = await getDocs(q);
    const docSnap = snap.docs[0];
    return docSnap ? docSnap.id : null;
  } catch (error) {
    console.error("[resolveIdentityDocId] error:", error);
    return null;
  }
}

// ---------- Hook ----------

export type NotificationsOptions = {
  onlyUnseen?: boolean;
  includeExpired?: boolean; // default false (i.e., exclude expired)
  pageSize?: number;        // default 50
};

export function useNotificationsListener(params: {
  db: Firestore;
  identityDocId?: string;
  userId?: string;
  options?: NotificationsOptions;
  onChange?: (items: Notification[]) => void;
}) {
  const { db, identityDocId, userId, options = {}, onChange } = params;

  const unsubRef = React.useRef<Unsubscribe | null>(null);
  const [items, setItems] = React.useState<Notification[]>([]);
  const [resolvedId, setResolvedId] = React.useState<string | null>(identityDocId ?? null);
  const [error, setError] = React.useState<string | null>(null);

  // NEW: keep onChange stable for the subscription effect
  const onChangeRef = React.useRef<typeof onChange>(onChange);
  React.useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

  // Resolve identity doc id via userId if needed
  React.useEffect(() => {
    let active = true;
    if (identityDocId) {
      setResolvedId(identityDocId);
      setError(null);
      return;
    }
    if (!userId) {
      setResolvedId(null);
      setError(null);
      return;
    }
    
    resolveIdentityDocIdByUserId(db, userId)
      .then((id) => {
        if (active) {
          setResolvedId(id);
          setError(id ? null : "Identity document not found");
        }
      })
      .catch((err) => {
        if (active) {
          console.error("[useNotificationsListener] resolve error:", err);
          setResolvedId(null);
          setError("Failed to resolve identity document");
        }
      });
    
    return () => { active = false; };
  }, [db, identityDocId, userId]);

  // Subscribe with better error handling
  React.useEffect(() => {
    if (unsubRef.current) { 
      unsubRef.current(); 
      unsubRef.current = null; 
    }

    if (!resolvedId) {
      setItems([]);
      setError(error || null); // Preserve existing error if no resolvedId
      onChangeRef.current?.([]);
      return;
    }

    try {
      const notificationsCol = collection(
        doc(db, "identity", resolvedId),
        "notifications"
      ).withConverter(notificationConverter) as CollectionReference<Notification>;

      const constraints: QueryConstraint[] = [];
      const pageSize = Math.min(options.pageSize ?? 50, 100); // Cap at 100 for safety

      if (options.onlyUnseen) {
        // Equality filter + orderBy(ts) is fine with built-in index
        constraints.push(where("seen", "==", false), orderBy("ts", "desc"), qLimit(pageSize));
      } else {
        constraints.push(orderBy("ts", "desc"), qLimit(pageSize));
      }

      const qRef: Query<Notification> = query(notificationsCol, ...constraints);

      const unsub = onSnapshot(
        qRef,
        (qs) => {
          let list = qs.docs.map((d) => d.data());

          // Sort by timestamp desc if we didn't order server-side
          if (options.onlyUnseen) {
            list.sort((a, b) => (b.ts?.getTime() || 0) - (a.ts?.getTime() || 0));
          }

          // Filter expired notifications client-side
          if (!options.includeExpired) {
            const now = Date.now();
            list = list.filter((n) => !n.expiresAt || n.expiresAt.getTime() >= now);
          }

          setItems(list);
          setError(null);
          onChangeRef.current?.(list);
        },
        (err) => {
          console.error("[notifications] snapshot error:", {
            code: (err as any)?.code,
            message: (err as any)?.message,
            details: err
          });
          
          setItems([]);
          setError(`Notification subscription failed: ${(err as any)?.code || 'Unknown error'}`);
          onChangeRef.current?.([]);
        }
      );

      unsubRef.current = unsub;
      return () => { 
        unsub(); 
        unsubRef.current = null; 
      };
    } catch (err) {
      console.error("[notifications] setup error:", err);
      setError(`Failed to setup notifications: ${err}`);
      setItems([]);
      onChangeRef.current?.([]);
    }
  }, [db, resolvedId, options.onlyUnseen, options.includeExpired, options.pageSize]);

  const actions = React.useMemo(() => {
    return {
      async markSeen(notifId: string, seen = true) {
        if (!resolvedId) throw new Error("No identity document resolved");
        const ref = doc(db, "identity", resolvedId, "notifications", notifId);
        await updateDoc(ref, { seen });
      },
      async markAllSeen(maxBatch = 100) {
        if (!resolvedId) throw new Error("No identity document resolved");
        const colRef = collection(db, "identity", resolvedId, "notifications");
        const snap = await getDocs(query(colRef, where("seen", "==", false), qLimit(maxBatch)));
        if (snap.empty) return;
        const batch = writeBatch(db);
        snap.forEach((d) => batch.update(d.ref, { seen: true }));
        await batch.commit();
      },
      async remove(notifId: string) {
        if (!resolvedId) throw new Error("No identity document resolved");
        const ref = doc(db, "identity", resolvedId, "notifications", notifId);
        await deleteDoc(ref);
      },
    };
  }, [db, resolvedId]);

  return { items, identityDocId: resolvedId, error, ...actions };
}

// ---------- JSX Component ----------

type ComponentProps = {
  db: Firestore;
  identityDocId?: string;
  userId?: string;
  onChange: (items: Notification[]) => void;
} & NotificationsOptions;

/** React component that subscribes to notifications and calls `onChange`. */
export function NotificationsListener(props: ComponentProps) {
  useNotificationsListener({
    db: props.db,
    identityDocId: props.identityDocId,
    userId: props.userId,
    options: {
      onlyUnseen: props.onlyUnseen,
      includeExpired: props.includeExpired,
      pageSize: props.pageSize,
    },
    onChange: props.onChange,
  });

  return null;
}

export default NotificationsListener;

// ---------- Standalone helpers ----------

export async function markNotificationSeen(
  db: Firestore,
  identityDocId: string,
  notifId: string,
  seen = true
) {
  const ref = doc(db, "identity", identityDocId, "notifications", notifId);
  await updateDoc(ref, { seen });
}

export async function markAllNotificationsSeen(
  db: Firestore,
  identityDocId: string,
  maxBatch = 100
) {
  const colRef = collection(db, "identity", identityDocId, "notifications");
  const snap = await getDocs(
    query(colRef, where("seen", "==", false), qLimit(maxBatch))
  );
  if (snap.empty) return;
  const batch = writeBatch(db);
  snap.forEach((d) => batch.update(d.ref, { seen: true }));
  await batch.commit();
}

export async function deleteNotification(
  db: Firestore,
  identityDocId: string,
  notifId: string
) {
  const ref = doc(db, "identity", identityDocId, "notifications", notifId);
  await deleteDoc(ref);
}