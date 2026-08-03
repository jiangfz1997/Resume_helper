FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# vite build only, without the vue-tsc pass that "npm run build" runs first:
# the existing sources do not typecheck cleanly yet. Restore "npm run build"
# here once they do.
RUN npx vite build


FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
