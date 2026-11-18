# build stage
FROM node:lts-alpine AS build-stage
# Set environment variables for non-interactive npm installs
ENV NPM_CONFIG_LOGLEVEL warn
ENV CI true
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm i --frozen-lockfile
COPY . .
# Để trống = frontend tự dùng cùng hostname + port 8000 lúc runtime (hợp deploy LAN/WG).
# Muốn cố định API khác: docker build --build-arg VITE_CONVERTER_API_URL=https://converter.example.com
ARG VITE_CONVERTER_API_URL=
ENV VITE_CONVERTER_API_URL=$VITE_CONVERTER_API_URL
RUN pnpm build

# production stage
FROM nginx:stable-alpine AS production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
