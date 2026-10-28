-- Kikan - suivi des actifs et remise de materiel signee
-- Copyright (C) 2026 Gabriel Chollet - GPLv3
-- Developpe avec l'assistance d'une IA (Claude, Anthropic).
--
-- Supprime les donnees creees par tests/security_check.py et tests/functional_smoke.py
-- (marquees ZZ...). A lancer sur une instance de DEVELOPPEMENT uniquement :
--   docker exec -i kikan-db psql -U kikan -d kikan -v ON_ERROR_STOP=1 < tests/cleanup_test_data.sql
--
-- Les PDF scelles orphelins restent dans le volume /archive (a supprimer a la main si besoin).
-- Le journal d'audit n'est volontairement PAS vide (il est append-only).

BEGIN;
CREATE TEMP TABLE tu AS SELECT id FROM users WHERE matricule LIKE 'ZZ%' OR prenom LIKE 'ZZ%';
CREATE TEMP TABLE ta AS SELECT id FROM assignments WHERE user_id IN (SELECT id FROM tu);
DELETE FROM besoins WHERE user_id IN (SELECT id FROM tu) OR assignment_id IN (SELECT id FROM ta);
DELETE FROM signatures WHERE assignment_id IN (SELECT id FROM ta);
DELETE FROM assignment_assets WHERE assignment_id IN (SELECT id FROM ta);
DELETE FROM assignments WHERE id IN (SELECT id FROM ta);
DELETE FROM user_applications WHERE user_id IN (SELECT id FROM tu);
DELETE FROM users WHERE id IN (SELECT id FROM tu);
DELETE FROM assignment_assets WHERE asset_id IN (SELECT id FROM assets WHERE numero_serie LIKE 'ZZ%');
DELETE FROM assets WHERE numero_serie LIKE 'ZZ%' OR marque LIKE 'ZZ%';
DELETE FROM user_applications WHERE application_id IN (SELECT id FROM applications WHERE nom LIKE 'ZZ%');
DELETE FROM applications WHERE nom LIKE 'ZZ%';
DELETE FROM account_scopes WHERE account_id IN (SELECT id FROM accounts WHERE username LIKE 'sec\_%' OR username LIKE '%@exemple.test' OR sso_upn LIKE '%@exemple.test')
  OR entite_id IN (SELECT id FROM entite WHERE code LIKE 'ZZ%');
DELETE FROM api_token_scopes WHERE token_id IN (SELECT id FROM api_tokens WHERE nom LIKE 'ZZ%')
  OR entite_id IN (SELECT id FROM entite WHERE code LIKE 'ZZ%');
DELETE FROM api_tokens WHERE nom LIKE 'ZZ%';
DELETE FROM external_links WHERE systeme LIKE 'zz%';
UPDATE assignments SET policy_id = NULL WHERE policy_id IN (SELECT id FROM policies WHERE titre LIKE 'ZZ%');
DELETE FROM policies WHERE titre LIKE 'ZZ%' OR entite_id IN (SELECT id FROM entite WHERE code LIKE 'ZZ%');
DELETE FROM entite WHERE code LIKE 'ZZ%';
DELETE FROM accounts WHERE username LIKE 'sec\_%' OR username LIKE '%@exemple.test' OR sso_upn LIKE '%@exemple.test';
DELETE FROM settings WHERE key LIKE 'sso\_%' OR key = 'session_ttl_min';
-- Les types d'actifs et services s'enrichissent seuls (liste souple) : on retire ceux qui ne servent plus.
-- (Instance de developpement uniquement : cela retire aussi un type ou service cree a la main et inutilise.)
DELETE FROM asset_types t WHERE NOT EXISTS (SELECT 1 FROM assets a WHERE lower(a.type) = lower(t.nom));
DELETE FROM services s WHERE NOT EXISTS (SELECT 1 FROM users u WHERE lower(u.service) = lower(s.nom));
DELETE FROM settings WHERE key LIKE 'pdf\_%';
DELETE FROM settings WHERE key LIKE 'mail\_%' OR key LIKE 'rappel\_%' OR key LIKE 'rapport\_%';
DELETE FROM reminder_sent WHERE destinataire LIKE '%@exemple.test';
DELETE FROM settings WHERE key = 'remise_inclure_acces';
COMMIT;
