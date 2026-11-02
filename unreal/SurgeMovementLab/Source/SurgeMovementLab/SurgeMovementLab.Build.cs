using UnrealBuildTool;
public class SurgeMovementLab : ModuleRules
{
    public SurgeMovementLab(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "AIModule", "NavigationSystem", "Json"
        });
        PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore", "ApplicationCore" });
    }
}
