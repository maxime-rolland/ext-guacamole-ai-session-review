package edu.example.guacamole.ai.dao;

import edu.example.guacamole.ai.model.SessionAiSummary;
import edu.example.guacamole.ai.model.SuspiciousEvent;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class SessionAiSummaryDao {

    private final String jdbcUrl;
    private final String username;
    private final String password;

    public SessionAiSummaryDao(String hostname, int port, String database,
                               String username, String password) {
        this.jdbcUrl = "jdbc:mysql://" + hostname + ":" + port + "/" + database
                     + "?useUnicode=true&characterEncoding=utf8"
                     + "&useSSL=false&allowPublicKeyRetrieval=true";
        this.username = username;
        this.password = password;
    }

    private Connection open() throws SQLException {
        return DriverManager.getConnection(jdbcUrl, username, password);
    }

    public List<SessionAiSummary> listAll() throws SQLException {
        String sql =
            "SELECT history_uuid, username, connection_name, started_at, "
          + "       ended_at, status, summary, risk_level, error, "
          + "       created_at, updated_at "
          + "FROM session_ai_summary "
          + "ORDER BY COALESCE(started_at, created_at) DESC";
        List<SessionAiSummary> out = new ArrayList<>();
        try (Connection c = open();
             PreparedStatement ps = c.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                out.add(mapSummary(rs));
            }
        }
        return out;
    }

    public Optional<SessionAiSummary> findByUuid(String historyUuid) throws SQLException {
        String sql =
            "SELECT history_uuid, username, connection_name, started_at, "
          + "       ended_at, status, summary, risk_level, error, "
          + "       created_at, updated_at "
          + "FROM session_ai_summary WHERE history_uuid = ?";
        try (Connection c = open();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, historyUuid);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) return Optional.of(mapSummary(rs));
                return Optional.empty();
            }
        }
    }

    public List<SuspiciousEvent> listEvents(String historyUuid) throws SQLException {
        String sql =
            "SELECT id, history_uuid, event_time_seconds, severity, category, "
          + "       description, evidence, created_at "
          + "FROM suspicious_event WHERE history_uuid = ? "
          + "ORDER BY event_time_seconds, id";
        List<SuspiciousEvent> out = new ArrayList<>();
        try (Connection c = open();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, historyUuid);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    SuspiciousEvent e = new SuspiciousEvent();
                    e.setId(rs.getLong("id"));
                    e.setHistoryUuid(rs.getString("history_uuid"));
                    int evt = rs.getInt("event_time_seconds");
                    e.setEventTimeSeconds(rs.wasNull() ? null : evt);
                    e.setSeverity(rs.getString("severity"));
                    e.setCategory(rs.getString("category"));
                    e.setDescription(rs.getString("description"));
                    e.setEvidence(rs.getString("evidence"));
                    e.setCreatedAt(isoOrNull(rs.getTimestamp("created_at")));
                    out.add(e);
                }
            }
        }
        return out;
    }

    private SessionAiSummary mapSummary(ResultSet rs) throws SQLException {
        SessionAiSummary s = new SessionAiSummary();
        s.setHistoryUuid(rs.getString("history_uuid"));
        s.setUsername(rs.getString("username"));
        s.setConnectionName(rs.getString("connection_name"));
        s.setStartedAt(isoOrNull(rs.getTimestamp("started_at")));
        s.setEndedAt(isoOrNull(rs.getTimestamp("ended_at")));
        s.setStatus(rs.getString("status"));
        s.setSummary(rs.getString("summary"));
        s.setRiskLevel(rs.getString("risk_level"));
        s.setError(rs.getString("error"));
        s.setCreatedAt(isoOrNull(rs.getTimestamp("created_at")));
        s.setUpdatedAt(isoOrNull(rs.getTimestamp("updated_at")));
        return s;
    }

    private static String isoOrNull(Timestamp ts) {
        return ts == null ? null : DateTimeFormatter.ISO_INSTANT.format(ts.toInstant());
    }

}
