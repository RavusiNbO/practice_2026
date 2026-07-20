COMPOSE ?= docker compose
MCP_SERVICE ?= mcp
PDF ?=

.PHONY: help up down build restart logs ps init-loki index add-pdf

help: ## Показать доступные команды
	@awk 'BEGIN {FS = ":.*##"; printf "Использование: make <цель>\n\nЦели:\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Собрать образы и запустить все сервисы в фоне
	$(COMPOSE) up -d --build

down: ## Остановить и удалить контейнеры
	$(COMPOSE) down

build: ## Пересобрать образы
	$(COMPOSE) build

restart: ## Перезапустить все сервисы
	$(COMPOSE) restart

logs: ## Показать логи всех сервисов
	$(COMPOSE) logs -f

ps: ## Показать состояние сервисов
	$(COMPOSE) ps

init-loki: ## Настроить отправку логов в Loki
	$(COMPOSE) exec -T $(MCP_SERVICE) python3 loki_init.py

index: ## Переиндексировать все PDF из server/documents
	$(COMPOSE) exec -T $(MCP_SERVICE) python3 index_documents.py

add-pdf: ## Скопировать PDF: make add-pdf PDF="/путь/к/файлу.pdf"
	@[ -n "$(PDF)" ] || { echo 'Укажите PDF: make add-pdf PDF="/путь/к/файлу.pdf"'; exit 2; }
	@[ -f "$(PDF)" ] || { echo "Файл не найден: $(PDF)"; exit 2; }
	@case "$(PDF)" in *.pdf|*.PDF) ;; *) echo "Ожидается PDF: $(PDF)"; exit 2;; esac
	@[ ! -e "server/documents/$(notdir $(PDF))" ] || { echo "Файл уже существует: server/documents/$(notdir $(PDF))"; exit 2; }
	@mkdir -p server/documents
	@cp "$(PDF)" "server/documents/$(notdir $(PDF))"
	@echo "Добавлен: server/documents/$(notdir $(PDF))"
	@echo "Теперь выполните: make index"
