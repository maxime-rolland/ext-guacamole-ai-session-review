package edu.example.guacamole.ai;

import edu.example.guacamole.ai.dao.SessionAiSummaryDao;
import edu.example.guacamole.ai.rest.AiReviewResource;

import org.apache.guacamole.GuacamoleException;
import org.apache.guacamole.net.auth.AbstractUserContext;
import org.apache.guacamole.net.auth.AuthenticatedUser;
import org.apache.guacamole.net.auth.AuthenticationProvider;
import org.apache.guacamole.net.auth.User;
import org.apache.guacamole.net.auth.simple.SimpleUser;

public class AiReviewUserContext extends AbstractUserContext {

    private final AuthenticationProvider authProvider;
    private final User self;
    private final SessionAiSummaryDao dao;

    public AiReviewUserContext(AuthenticationProvider authProvider,
                               AuthenticatedUser authenticatedUser,
                               SessionAiSummaryDao dao) {
        this.authProvider = authProvider;
        this.self = new SimpleUser(authenticatedUser.getIdentifier());
        this.dao = dao;
    }

    @Override
    public AuthenticationProvider getAuthenticationProvider() {
        return authProvider;
    }

    @Override
    public User self() {
        return self;
    }

    @Override
    public Object getResource() throws GuacamoleException {
        return new AiReviewResource(dao);
    }

    @Override
    public void invalidate() {
        // no-op: pas d'état per-session
    }

}
