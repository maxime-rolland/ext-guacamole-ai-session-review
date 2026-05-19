package edu.example.guacamole.ai;

import edu.example.guacamole.ai.dao.SessionAiSummaryDao;

import org.apache.guacamole.GuacamoleException;
import org.apache.guacamole.environment.Environment;
import org.apache.guacamole.environment.LocalEnvironment;
import org.apache.guacamole.net.auth.AbstractAuthenticationProvider;
import org.apache.guacamole.net.auth.AuthenticatedUser;
import org.apache.guacamole.net.auth.UserContext;

public class AiReviewAuthenticationProvider extends AbstractAuthenticationProvider {

    public static final String IDENTIFIER = "ai-session-review";

    private final SessionAiSummaryDao dao;

    public AiReviewAuthenticationProvider() throws GuacamoleException {
        Environment env = LocalEnvironment.getInstance();
        String host = env.getProperty(AiReviewProperties.AI_REVIEW_DB_HOSTNAME, "localhost");
        int    port = env.getProperty(AiReviewProperties.AI_REVIEW_DB_PORT, 3306);
        String db   = env.getProperty(AiReviewProperties.AI_REVIEW_DB_DATABASE, "guacamoledb");
        String user = env.getRequiredProperty(AiReviewProperties.AI_REVIEW_DB_USERNAME);
        String pwd  = env.getRequiredProperty(AiReviewProperties.AI_REVIEW_DB_PASSWORD);
        this.dao = new SessionAiSummaryDao(host, port, db, user, pwd);
    }

    @Override
    public String getIdentifier() {
        return IDENTIFIER;
    }

    @Override
    public UserContext getUserContext(AuthenticatedUser authenticatedUser)
            throws GuacamoleException {
        return new AiReviewUserContext(this, authenticatedUser, dao);
    }

}
