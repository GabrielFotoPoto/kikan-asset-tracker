# Kikan

Suivi des actifs et remise de materiel signee (voir `SPEC.md`).

Pile : React (front, a venir) + FastAPI (Python) + PostgreSQL, en conteneurs Docker.

## Demarrage (developpement)

```
cp .env.example .env        # puis editer POSTGRES_PASSWORD
docker compose up --build
```

- API : http://localhost:8080
- Documentation interactive : http://localhost:8080/docs
- Sante : http://localhost:8080/health

## Etat

v0.1 en construction. Fait : modele de donnees, API CRUD (entites, utilisateurs,
actifs, applications), autocompletion marques/modeles. A venir : affectations et
remise signee (PDF scelle PAdES), import CSV, front React, authentification.

## Structure

```
backend/        API FastAPI
  app/
    models.py   modele de donnees (SQLModel)
    routers/    endpoints CRUD
import-modeles/ modeles CSV pour la reprise de l'existant
docker-compose.yml
```
