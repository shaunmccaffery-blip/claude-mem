# SaaS MVP (Next.js + Prisma + Stripe)

A minimal, production-ready SaaS MVP that supports:

- Email sign-up/login (NextAuth)
- Text input ingestion (paste/upload-ready API)
- Automated report generation (template + optional OpenAI)
- Dashboard for reports
- Email notifications (Resend)
- Stripe subscription checkout + webhook
- Scheduled background run endpoint (`/api/jobs/run`)

## Tech

- Next.js 14 (App Router, TypeScript)
- TailwindCSS
- PostgreSQL + Prisma
- NextAuth (Email provider)
- Stripe
- Resend

## Local setup

1. Copy env values:
   ```bash
   cp .env.example .env
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Initialize Prisma:
   ```bash
   npx prisma generate
   npx prisma db push
   ```
4. Run development server:
   ```bash
   npm run dev
   ```

## Key routes

- `/auth/signup` / `/auth/login`
- `/dashboard`
- `/new-report`
- `POST /api/jobs/run` (requires `X-JOB-SECRET` header)
- `POST /api/webhooks/stripe`

## Stripe webhook local testing

```bash
stripe listen --forward-to localhost:3000/api/webhooks/stripe
```

## Google Cloud Run deploy

```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud builds submit --tag gcr.io/YOUR_GCP_PROJECT_ID/saas-mvp
gcloud run deploy saas-mvp \
  --image gcr.io/YOUR_GCP_PROJECT_ID/saas-mvp \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars NODE_ENV=production
```

Set your full application env vars in Cloud Run (Secret Manager recommended).

## Cron/background execution

Call the job endpoint periodically from Cloud Scheduler:

- URL: `https://<service-url>/api/jobs/run`
- Method: `POST`
- Header: `X-JOB-SECRET: <JOB_SECRET>`
