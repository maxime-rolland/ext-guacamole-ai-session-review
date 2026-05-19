package edu.example.guacamole.ai.model;

public class SessionAiSummary {

    private String historyUuid;
    private String username;
    private String connectionName;
    private String startedAt;
    private String endedAt;
    private String status;
    private String summary;
    private String riskLevel;
    private String error;
    private String createdAt;
    private String updatedAt;

    public String getHistoryUuid()    { return historyUuid; }
    public String getUsername()       { return username; }
    public String getConnectionName() { return connectionName; }
    public String getStartedAt()     { return startedAt; }
    public String getEndedAt()       { return endedAt; }
    public String getStatus()         { return status; }
    public String getSummary()        { return summary; }
    public String getRiskLevel()      { return riskLevel; }
    public String getError()          { return error; }
    public String getCreatedAt()     { return createdAt; }
    public String getUpdatedAt()     { return updatedAt; }

    public void setHistoryUuid(String v)    { this.historyUuid = v; }
    public void setUsername(String v)       { this.username = v; }
    public void setConnectionName(String v) { this.connectionName = v; }
    public void setStartedAt(String v)     { this.startedAt = v; }
    public void setEndedAt(String v)       { this.endedAt = v; }
    public void setStatus(String v)         { this.status = v; }
    public void setSummary(String v)        { this.summary = v; }
    public void setRiskLevel(String v)      { this.riskLevel = v; }
    public void setError(String v)          { this.error = v; }
    public void setCreatedAt(String v)     { this.createdAt = v; }
    public void setUpdatedAt(String v)     { this.updatedAt = v; }

}
