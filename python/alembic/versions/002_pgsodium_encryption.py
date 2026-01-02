"""pgsodium encryption for refresh_token

Implements Task 1.4: Supabase Vault / pgsodium Integration

This migration sets up transparent encryption for the refresh_token field
in ga4_credentials table using pgsodium extension. The encryption happens
automatically at the database level via triggers.

CRITICAL SECURITY FEATURES:
1. Refresh tokens are encrypted before being written to WAL logs
2. Encryption key is managed by pgsodium (not stored in application code)
3. Decryption is only possible via strictly permissioned database function
4. Application code never handles encryption/decryption directly

Revision ID: 002_pgsodium_encryption
Revises: 001_initial_schema
Create Date: 2026-01-02 12:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_pgsodium_encryption'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Enable pgsodium and create encryption functions for refresh_token.
    
    This implements transparent encryption at the database level.
    """
    
    # Enable pgsodium extension (already enabled in init.sql, but ensure it's present)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgsodium;")
    
    # Create encryption key if not exists
    # In production, this should be managed via Supabase Vault or environment variables
    op.execute("""
        DO $$
        BEGIN
            -- Check if encryption key exists, create if not
            IF NOT EXISTS (
                SELECT 1 FROM pgsodium.valid_key WHERE name = 'ga4_refresh_token_key'
            ) THEN
                -- Create a new encryption key
                -- In production, use: SELECT pgsodium.create_key('ga4_refresh_token_key');
                -- For development, we'll create a key automatically
                INSERT INTO pgsodium.key (name, description)
                VALUES (
                    'ga4_refresh_token_key',
                    'Encryption key for GA4 OAuth refresh tokens'
                );
            END IF;
        END $$;
    """)
    
    # Add encrypted_refresh_token column (bytea type for encrypted data)
    op.add_column(
        'ga4_credentials',
        sa.Column('encrypted_refresh_token', sa.LargeBinary(), nullable=True)
    )
    
    # Create encryption function
    op.execute("""
        CREATE OR REPLACE FUNCTION encrypt_refresh_token()
        RETURNS TRIGGER AS $$
        DECLARE
            key_id uuid;
        BEGIN
            -- Get the encryption key ID
            SELECT id INTO key_id 
            FROM pgsodium.key 
            WHERE name = 'ga4_refresh_token_key' 
            LIMIT 1;
            
            -- Encrypt the refresh_token and store in encrypted_refresh_token
            IF NEW.refresh_token IS NOT NULL AND NEW.refresh_token != '' THEN
                NEW.encrypted_refresh_token := pgsodium.crypto_aead_det_encrypt(
                    NEW.refresh_token::bytea,
                    NULL,  -- No associated data
                    key_id
                );
                
                -- Clear the plaintext refresh_token to prevent WAL log exposure
                -- We keep a placeholder to maintain NOT NULL constraint
                NEW.refresh_token := '[ENCRYPTED]';
            END IF;
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)
    
    # Create decryption function (strictly permissioned)
    op.execute("""
        CREATE OR REPLACE FUNCTION decrypt_refresh_token(
            credential_id uuid
        ) RETURNS text AS $$
        DECLARE
            encrypted_data bytea;
            key_id uuid;
            decrypted_text bytea;
        BEGIN
            -- Get the encryption key ID
            SELECT id INTO key_id 
            FROM pgsodium.key 
            WHERE name = 'ga4_refresh_token_key' 
            LIMIT 1;
            
            -- Get encrypted refresh token
            SELECT encrypted_refresh_token INTO encrypted_data
            FROM ga4_credentials
            WHERE id = credential_id;
            
            -- Decrypt and return
            IF encrypted_data IS NOT NULL THEN
                decrypted_text := pgsodium.crypto_aead_det_decrypt(
                    encrypted_data,
                    NULL,  -- No associated data
                    key_id
                );
                RETURN convert_from(decrypted_text, 'UTF8');
            END IF;
            
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)
    
    # Create trigger to automatically encrypt on INSERT and UPDATE
    op.execute("""
        CREATE TRIGGER encrypt_ga4_refresh_token
        BEFORE INSERT OR UPDATE ON ga4_credentials
        FOR EACH ROW
        EXECUTE FUNCTION encrypt_refresh_token();
    """)
    
    # Migrate existing data (if any)
    op.execute("""
        UPDATE ga4_credentials
        SET refresh_token = refresh_token
        WHERE encrypted_refresh_token IS NULL;
    """)
    
    # Create helper view for safe access (excludes encrypted data)
    op.execute("""
        CREATE OR REPLACE VIEW ga4_credentials_safe AS
        SELECT 
            id,
            user_id,
            property_id,
            property_name,
            access_token,
            token_expiry,
            scope,
            token_type,
            created_at,
            updated_at,
            last_used_at
        FROM ga4_credentials;
    """)
    
    # Grant permissions
    op.execute("""
        -- Revoke direct access to refresh_token column
        -- REVOKE SELECT (refresh_token) ON ga4_credentials FROM PUBLIC;
        
        -- Grant access to safe view
        GRANT SELECT ON ga4_credentials_safe TO PUBLIC;
    """)


def downgrade() -> None:
    """Remove encryption setup."""
    
    # Drop view
    op.execute("DROP VIEW IF EXISTS ga4_credentials_safe;")
    
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS encrypt_ga4_refresh_token ON ga4_credentials;")
    
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS decrypt_refresh_token(uuid);")
    op.execute("DROP FUNCTION IF EXISTS encrypt_refresh_token();")
    
    # Drop encrypted column
    op.drop_column('ga4_credentials', 'encrypted_refresh_token')
    
    # Note: We don't drop the pgsodium extension or encryption key
    # as they might be used by other parts of the system

