package edu.example.guacamole.ai.rest;

import edu.example.guacamole.ai.dao.SessionAiSummaryDao;
import edu.example.guacamole.ai.model.SessionAiSummary;
import edu.example.guacamole.ai.model.SuspiciousEvent;

import java.sql.SQLException;
import java.util.List;
import java.util.UUID;
import javax.ws.rs.BadRequestException;
import javax.ws.rs.GET;
import javax.ws.rs.InternalServerErrorException;
import javax.ws.rs.NotFoundException;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;

// V1 : tout utilisateur authentifié peut consulter. Le filtrage par
// rôle administrateur est prévu dans le lot 5 (sécurité avancée).
@Produces(MediaType.APPLICATION_JSON)
public class AiReviewResource {

    private final SessionAiSummaryDao dao;

    public AiReviewResource(SessionAiSummaryDao dao) {
        this.dao = dao;
    }

    @GET
    @Path("summaries")
    public List<SessionAiSummary> listSummaries() {
        try {
            return dao.listAll();
        } catch (SQLException e) {
            throw new InternalServerErrorException("DB error: " + e.getMessage(), e);
        }
    }

    @GET
    @Path("summaries/{historyUuid}")
    public SessionAiSummary getSummary(@PathParam("historyUuid") String historyUuid) {
        String validated = validateUuid(historyUuid);
        try {
            return dao.findByUuid(validated)
                    .orElseThrow(() -> new NotFoundException(
                        "No AI summary for session " + validated));
        } catch (SQLException e) {
            throw new InternalServerErrorException("DB error: " + e.getMessage(), e);
        }
    }

    @GET
    @Path("summaries/{historyUuid}/events")
    public List<SuspiciousEvent> listEvents(@PathParam("historyUuid") String historyUuid) {
        String validated = validateUuid(historyUuid);
        try {
            return dao.listEvents(validated);
        } catch (SQLException e) {
            throw new InternalServerErrorException("DB error: " + e.getMessage(), e);
        }
    }

    private static String validateUuid(String raw) {
        try {
            return UUID.fromString(raw).toString();
        } catch (IllegalArgumentException e) {
            throw new BadRequestException("Invalid history UUID: " + raw);
        }
    }

}
