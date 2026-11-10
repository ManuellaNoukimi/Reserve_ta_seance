-- À exécuter sur une base déjà créée (avant ce changement, Donner n’avait que note + date).
-- Nouvelles colonnes : commentaire libre + tags (JSON tableau de clés, ex. ["ponctuel","participation"]).

ALTER TABLE Donner
  ADD COLUMN commentaire TEXT NULL AFTER note,
  ADD COLUMN tags VARCHAR(512) NULL AFTER commentaire;
