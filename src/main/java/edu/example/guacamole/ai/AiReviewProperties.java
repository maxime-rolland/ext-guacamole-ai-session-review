package edu.example.guacamole.ai;

import org.apache.guacamole.properties.IntegerGuacamoleProperty;
import org.apache.guacamole.properties.StringGuacamoleProperty;

/**
 * Propriétés lues depuis guacamole.properties (ou variables
 * d'environnement, via enable-environment-properties: true qui est
 * actif par défaut dans l'image officielle).
 *
 * Convention env var : "ai-review-db-hostname" est exposé comme
 * AI_REVIEW_DB_HOSTNAME (upper-case + tirets→underscore).
 */
public final class AiReviewProperties {

    private AiReviewProperties() {}

    public static final StringGuacamoleProperty AI_REVIEW_DB_HOSTNAME =
            new StringGuacamoleProperty() {
                @Override public String getName() { return "ai-review-db-hostname"; }
            };

    public static final IntegerGuacamoleProperty AI_REVIEW_DB_PORT =
            new IntegerGuacamoleProperty() {
                @Override public String getName() { return "ai-review-db-port"; }
            };

    public static final StringGuacamoleProperty AI_REVIEW_DB_DATABASE =
            new StringGuacamoleProperty() {
                @Override public String getName() { return "ai-review-db-database"; }
            };

    public static final StringGuacamoleProperty AI_REVIEW_DB_USERNAME =
            new StringGuacamoleProperty() {
                @Override public String getName() { return "ai-review-db-username"; }
            };

    public static final StringGuacamoleProperty AI_REVIEW_DB_PASSWORD =
            new StringGuacamoleProperty() {
                @Override public String getName() { return "ai-review-db-password"; }
            };

}
