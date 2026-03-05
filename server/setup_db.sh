#!/bin/bash

# Golden Ledger – Database Setup & Migration Script
# Loads env from server/.env or falls back to the defaults below.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status()  { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

show_usage() {
    echo "=========================================="
    echo "    Golden Ledger – DB Setup & Migration  "
    echo "=========================================="
    echo
    echo "Usage: $0 [option]"
    echo
    echo "Options:"
    echo "  --setup-db    Create database and extensions"
    echo "  --migrate     Run Alembic migrations (alembic upgrade head)"
    echo "  --clear-data  Delete all deals & documents, keep auth data  ⚠"
    echo "  --drop-db     Drop the database  ⚠  DESTRUCTIVE"
    echo "  --reset-db    Drop + recreate + migrate  ⚠  DESTRUCTIVE"
    echo "  --help, -h    Show this help"
    echo
    echo "No option → interactive mode."
    echo
    echo "Defaults (override via server/.env or environment):"
    echo "  DB_HOST=localhost  DB_PORT=5432"
    echo "  DB_USER=lokamdb    DB_NAME=golden"
    echo
}

# ── Environment ───────────────────────────────────────────────────────────────

load_env_vars() {
    # Script lives in server/; resolve .env relative to this file
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    ENV_FILE="$SCRIPT_DIR/.env"

    if [ -f "$ENV_FILE" ]; then
        print_status "Loading environment from $ENV_FILE ..."
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
        print_success "Environment loaded"
    else
        print_warning ".env not found – using defaults"
    fi

    # Defaults matching the project credentials
    DB_HOST="${DB_HOST:-localhost}"
    DB_PORT="${DB_PORT:-5432}"
    DB_USER="${DB_USER:-lokamdb}"
    DB_PASSWORD="${DB_PASSWORD:-sanji}"
    DB_NAME="${DB_NAME:-golden}"

    # Build DATABASE_URL if not already set; or parse it back into components
    # so psql / pg_isready calls work regardless of which form was provided.
    if [ -z "${DATABASE_URL:-}" ]; then
        DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
    else
        # Parse DATABASE_URL → individual vars (handles Railway / any remote URL)
        eval "$(python3 - <<'PYEOF'
import os, sys
from urllib.parse import urlparse
u = urlparse(os.environ["DATABASE_URL"])
print(f'DB_HOST={u.hostname}')
print(f'DB_PORT={u.port or 5432}')
print(f'DB_USER={u.username or ""}')
print(f'DB_PASSWORD={u.password or ""}')
print(f'DB_NAME={u.path.lstrip("/")}')
PYEOF
        )"
    fi

    export DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME DATABASE_URL
}

display_config() {
    print_status "Configuration:"
    echo "  Host     : $DB_HOST"
    echo "  Port     : $DB_PORT"
    echo "  User     : $DB_USER"
    echo "  Database : $DB_NAME"
    echo "  URL      : postgresql://${DB_USER}:***@${DB_HOST}:${DB_PORT}/${DB_NAME}"
}

# ── Checks ────────────────────────────────────────────────────────────────────

check_postgres() {
    print_status "Checking PostgreSQL connection..."
    if PGPASSWORD="$DB_PASSWORD" pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" >/dev/null 2>&1; then
        print_success "PostgreSQL is reachable"
    else
        print_error "Cannot reach PostgreSQL at $DB_HOST:$DB_PORT as $DB_USER"
        print_error "Make sure PostgreSQL is running and the user exists."
        exit 1
    fi
}

check_alembic() {
    if ! command -v alembic &>/dev/null; then
        print_error "alembic not found. Run: pip install -r server/requirements.txt"
        exit 1
    fi
}

# ── Database operations ───────────────────────────────────────────────────────

create_database() {
    print_status "Creating database '$DB_NAME' ..."
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
        -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "$DB_NAME"; then
        print_success "Database '$DB_NAME' already exists – skipping"
        return 0
    fi
    PGPASSWORD="$DB_PASSWORD" createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
    print_success "Database '$DB_NAME' created"
}

create_extensions() {
    print_status "Installing extensions ..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";' >/dev/null
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -c 'CREATE EXTENSION IF NOT EXISTS "pgcrypto";' >/dev/null 2>&1 \
        || print_warning "pgcrypto extension skipped (not critical)"
    print_success "Extensions ready"
}

setup_database() {
    create_database
    create_extensions
    print_success "Database setup complete"
}

run_migrations() {
    check_alembic
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    print_status "Running migrations from $SCRIPT_DIR ..."
    # alembic.ini lives in server/, so run from there
    (cd "$SCRIPT_DIR" && alembic upgrade head)
    print_success "Migrations applied"
}

drop_database() {
    print_status "Dropping database '$DB_NAME' ..."
    if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
        -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "$DB_NAME"; then
        print_warning "Database '$DB_NAME' does not exist – nothing to drop"
        return 0
    fi
    # Terminate open connections first
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null 2>&1 \
        || true
    PGPASSWORD="$DB_PASSWORD" dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
    print_success "Database '$DB_NAME' dropped"
}

reset_database() {
    drop_database
    setup_database
    print_success "Database reset complete"
}

clear_deal_data() {
    print_status "Clearing documents and deals from '$DB_NAME' (auth data preserved) ..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -c "TRUNCATE TABLE documents, deals RESTART IDENTITY CASCADE;"
    print_success "documents and deals cleared — users table untouched"
}

# ── Interactive mode ──────────────────────────────────────────────────────────

main_interactive() {
    echo "=========================================="
    echo "    Golden Ledger – DB Setup & Migration  "
    echo "=========================================="
    echo
    load_env_vars
    display_config
    echo
    check_postgres
    echo
    echo "What would you like to do?"
    echo "  1) Setup database (create + extensions)"
    echo "  2) Run migrations"
    echo "  3) Setup database AND run migrations  ← recommended first-time"
    echo "  4) Clear deals & documents (keep auth data)  ⚠"
    echo "  5) Drop database  ⚠"
    echo "  6) Reset database (drop + recreate + migrate)  ⚠"
    echo "  7) Exit"
    echo
    read -rp "Choice (1-7): " choice
    echo

    case $choice in
        1) setup_database ;;
        2) run_migrations ;;
        3) setup_database && run_migrations ;;
        4)
            print_warning "This deletes all deals and documents in '$DB_NAME'. Users are preserved."
            read -rp "Type 'yes' to confirm: " confirm
            [ "$confirm" = "yes" ] && clear_deal_data || print_status "Cancelled"
            ;;
        5)
            print_warning "This permanently deletes '$DB_NAME'."
            read -rp "Type 'yes' to confirm: " confirm
            [ "$confirm" = "yes" ] && drop_database || print_status "Cancelled"
            ;;
        6)
            print_warning "This permanently deletes and recreates '$DB_NAME'."
            read -rp "Type 'yes' to confirm: " confirm
            [ "$confirm" = "yes" ] && reset_database && run_migrations || print_status "Cancelled"
            ;;
        7) print_status "Bye!"; exit 0 ;;
        *) print_error "Invalid choice"; exit 1 ;;
    esac

    echo
    print_success "Done! You can now start the server:"
    echo "  cd server && uvicorn app.main:app --reload"
}

# ── Entry point ───────────────────────────────────────────────────────────────

case "${1:-interactive}" in
    "--setup-db")
        load_env_vars; check_postgres; setup_database ;;
    "--migrate")
        load_env_vars; run_migrations ;;
    "--clear-data")
        load_env_vars; check_postgres
        print_warning "This deletes all deals and documents in '$DB_NAME'. Users are preserved."
        read -rp "Type 'yes' to confirm: " confirm
        [ "$confirm" = "yes" ] && clear_deal_data || print_status "Cancelled"
        ;;
    "--drop-db")
        load_env_vars; check_postgres
        print_warning "This permanently deletes '$DB_NAME'."
        read -rp "Type 'yes' to confirm: " confirm
        [ "$confirm" = "yes" ] && drop_database || print_status "Cancelled"
        ;;
    "--reset-db")
        load_env_vars; check_postgres
        print_warning "This permanently deletes and recreates '$DB_NAME'."
        read -rp "Type 'yes' to confirm: " confirm
        [ "$confirm" = "yes" ] && reset_database && run_migrations || print_status "Cancelled"
        ;;
    "--help"|"-h")
        show_usage ;;
    "interactive")
        main_interactive ;;
    *)
        print_error "Unknown option: $1"; echo; show_usage; exit 1 ;;
esac
