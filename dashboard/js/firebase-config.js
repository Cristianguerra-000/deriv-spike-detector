// Configuración Firebase Web SDK (claves públicas por diseño).
// La seguridad real se aplica con las "Reglas de Firestore", NO ocultando estas claves.
// El token de Deriv NUNCA debe vivir aquí ni en ningún archivo del navegador.

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getFirestore,
  collection,
  doc,
  getDoc,
  getDocs,
  onSnapshot,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

export const firebaseConfig = {
  apiKey: "AIzaSyBMyQxnXyvHhaGanfFLNyGdmLHMqiwzvxU",
  authDomain: "sofingia-website.firebaseapp.com",
  projectId: "sofingia-website",
  storageBucket: "sofingia-website.firebasestorage.app",
  messagingSenderId: "769629217931",
  appId: "1:769629217931:web:1e3ec3eb69b38d9689208e",
};

export const firebaseApp = initializeApp(firebaseConfig);
export const db = getFirestore(firebaseApp);

export { collection, doc, getDoc, getDocs, onSnapshot };
