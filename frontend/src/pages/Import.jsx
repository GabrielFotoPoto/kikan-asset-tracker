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
import { api, downloadFile, errorText, postForm } from "../api.js";

// Enregistre un texte (CSV) sur le poste, avec BOM pour une ouverture directe dans Excel.
function saveCsv(filename, text) {
  const blob = new Blob(["﻿", text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

// Import CSV : simulation (rien n'est ecrit), puis import reel du meme fichier, tout ou rien.
export default function Import() {
  const [specs, setSpecs] = useState([]);
  const [kind, setKind] = useState("entites");
  const [file, setFile] = useState(null);
  const [fileKey, setFileKey] = useState(0);
  const [report, setReport] = useState(null);
  const [final, setFinal] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => { api.get("/import/specs").then(setSpecs).catch((e) => setErr(errorText(e))); }, []);

  const spec = specs.find((s) => s.kind === kind);
  const next = specs.find((s) => s.ordre === (spec?.ordre || 0) + 1);

  const reset = (newKind) => {
    if (newKind) setKind(newKind);
    setFile(null); setReport(null); setFinal(null); setErr(null);
    setFileKey((k) => k + 1);
  };

  const simulate = async (f) => {
    setFile(f); setReport(null); setFinal(null); setErr(null);
    if (!f) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", f);
      setReport(await postForm(`/import/${kind}?dry_run=true`, form));
    } catch (ex) { setErr(errorText(ex)); } finally { setBusy(false); }
  };

  const importReal = async () => {
    setErr(null); setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      setFinal(await postForm(`/import/${kind}?strict=true&attendu=${report.sha256}`, form));
    } catch (ex) { setErr(errorText(ex)); } finally { setBusy(false); }
  };

  const exportErrors = () => {
    const lines = ["ligne;message", ...report.errors.map((e) => `${e.ligne};${cell(e.message)}`)];
    saveCsv(`erreurs_${kind}.csv`, lines.join("\r\n") + "\r\n");
  };

  const r = final || report;
  const clean = report && report.errors_total === 0 && report.imported > 0;

  return (
    <div>
      <h2>Import CSV</h2>
      <p className="muted">
        Reprise de l'existant. Le fichier est d'abord <b>simule</b> : rien n'est ecrit tant que vous ne confirmez pas.
        L'import ne fait que creer ; un element deja present est ignore. S'il reste une erreur, rien n'est importe.
      </p>
      {err && <p className="err">{err}</p>}

      <div className="card">
        <h3>1. Type de fichier</h3>
        <p className="muted" style={{ marginTop: 0 }}>Ordre conseille (chaque etape depend des precedentes) :</p>
        <div className="row" style={{ marginBottom: 8 }}>
          {specs.map((s) => (
            <button key={s.kind} className={s.kind === kind ? "" : "ghost"} onClick={() => reset(s.kind)}>
              {s.ordre}. {s.titre}
            </button>
          ))}
        </div>
        {spec && (
          <>
            <p>{spec.description}</p>
            <table>
              <thead><tr><th>Colonne</th><th>Obligatoire</th><th>Contenu attendu</th></tr></thead>
              <tbody>
                {spec.colonnes.map((c) => (
                  <tr key={c.nom}><td><code>{c.nom}</code></td><td>{c.obligatoire ? "oui" : "non"}</td><td>{c.aide}</td></tr>
                ))}
              </tbody>
            </table>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="ghost" onClick={() => downloadFile(`/import/modeles/${kind}`, `${kind}.csv`)}>
                Telecharger le modele CSV
              </button>
              <span className="muted">Encodage UTF-8 ou Windows-1252, separateur ; ou , (detectes automatiquement).</span>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <h3>2. Fichier et simulation</h3>
        <input key={fileKey} type="file" accept=".csv,.txt,text/csv" disabled={busy}
               onChange={(e) => simulate(e.target.files[0] || null)} />
        {busy && !final && <p className="muted">Simulation en cours...</p>}
      </div>

      {r && (
        <div className="card">
          <h3>{final ? "3. Import termine" : "3. Resultat de la simulation"}</h3>
          <div className="row" style={{ marginBottom: 10 }}>
            <span className="badge">Lignes lues : {r.total}</span>
            <span className="badge ok">{final ? "Creees" : "A creer"} : {r.imported}</span>
            <span className="badge">Ignorees : {r.skipped}</span>
            <span className={r.errors_total ? "badge bad" : "badge"}>Erreurs : {r.errors_total}</span>
          </div>
          <p className="muted" style={{ marginTop: 0 }}>
            Encodage {r.encodage}, separateur {r.separateur === ";" ? "point-virgule" : "virgule"}.
          </p>
          {r.colonnes_ignorees?.length > 0 && (
            <p className="warn">Colonnes non reconnues, ignorees : {r.colonnes_ignorees.join(", ")}.</p>
          )}

          {r.errors_total > 0 && (
            <>
              <h4>Erreurs a corriger dans le fichier</h4>
              <table>
                <thead><tr><th>Ligne</th><th>Probleme</th></tr></thead>
                <tbody>{r.errors.map((e, i) => <tr key={i}><td>{e.ligne}</td><td>{e.message}</td></tr>)}</tbody>
              </table>
              {r.errors_total > r.errors.length && (
                <p className="muted">Seules les {r.errors.length} premieres erreurs sont affichees ({r.errors_total} au total).</p>
              )}
            </>
          )}

          {r.lignes.length > 0 && (
            <details style={{ marginTop: 10 }}>
              <summary>Detail ligne par ligne ({r.lignes.length}{r.tronque ? "+" : ""})</summary>
              <table>
                <thead><tr><th>Ligne</th><th>Action</th><th>Detail</th></tr></thead>
                <tbody>
                  {r.lignes.map((l, i) => (
                    <tr key={i}><td>{l.ligne}</td><td>{l.action === "creer" ? (final ? "creee" : "sera creee") : "ignoree"}</td><td>{l.message}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}

          <div className="row" style={{ marginTop: 14 }}>
            {!final && (
              <button onClick={importReal} disabled={busy || !clean}>
                {busy ? "Import en cours..." : `Importer pour de bon (${report.imported})`}
              </button>
            )}
            {!final && r.errors_total > 0 && <button className="ghost" onClick={exportErrors}>Telecharger les erreurs (CSV)</button>}
            {final && next && <button onClick={() => reset(next.kind)}>Etape suivante : {next.titre}</button>}
            <button className="ghost" onClick={() => reset()}>{final ? "Nouvel import" : "Recommencer"}</button>
          </div>
          {!final && r.errors_total > 0 && (
            <p className="muted">Corrigez le fichier, puis deposez-le a nouveau : l'import reste bloque tant qu'il y a des erreurs.</p>
          )}
          {!final && r.errors_total === 0 && r.imported === 0 && (
            <p className="muted">Rien a importer : tous les elements existent deja.</p>
          )}
        </div>
      )}
    </div>
  );
}
