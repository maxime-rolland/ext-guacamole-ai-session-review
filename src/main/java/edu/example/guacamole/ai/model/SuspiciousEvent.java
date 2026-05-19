package edu.example.guacamole.ai.model;

public class SuspiciousEvent {

    private long id;
    private String historyUuid;
    private Integer eventTimeSeconds;
    private String severity;
    private String category;
    private String description;
    private String evidence;
    private String createdAt;

    public long getId()                  { return id; }
    public String getHistoryUuid()       { return historyUuid; }
    public Integer getEventTimeSeconds() { return eventTimeSeconds; }
    public String getSeverity()          { return severity; }
    public String getCategory()          { return category; }
    public String getDescription()       { return description; }
    public String getEvidence()          { return evidence; }
    public String getCreatedAt()        { return createdAt; }

    public void setId(long v)                    { this.id = v; }
    public void setHistoryUuid(String v)         { this.historyUuid = v; }
    public void setEventTimeSeconds(Integer v)   { this.eventTimeSeconds = v; }
    public void setSeverity(String v)            { this.severity = v; }
    public void setCategory(String v)            { this.category = v; }
    public void setDescription(String v)         { this.description = v; }
    public void setEvidence(String v)            { this.evidence = v; }
    public void setCreatedAt(String v)          { this.createdAt = v; }

}
