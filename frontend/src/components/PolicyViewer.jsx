/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Claude, Anthropic).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */


import { useEffect, useState } from "react";
import { fetchDataUrl } from "../api.js";

// Affiche les pages d'une charte (images rendues par le serveur), page apres page.
export default function PolicyViewer({ policyId, nbPages, maxHeight = 520 }) {
  const [pages, setPages] = useState([]);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let stop = false;
    setPages([]);
    setErr(null);
    (async () => {
      for (let n = 1; n <= nbPages; n += 1) {
        try {
          const url = await fetchDataUrl(`/policies/${policyId}/page/${n}`);
          if (stop) return;
          setPages((p) => [...p, url]);
        } catch (ex) {
          if (!stop) setErr(ex.message);
          return;
        }
      }
    })();
    return () => { stop = true; };
  }, [policyId, nbPages]);

  return (
    <div className="policy-viewer" style={{ maxHeight }}>
      {pages.map((src, i) => (
        <img key={i} src={src} alt={`Charte, page ${i + 1} sur ${nbPages}`} className="policy-page" />
      ))}
      {pages.length < nbPages && !err && <p className="muted">Chargement des pages...</p>}
      {err && <p className="err">{err}</p>}
    </div>
  );
}
