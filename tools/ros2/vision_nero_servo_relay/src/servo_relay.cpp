// Verified Servo windows -> official JTC, then source-checked references -> local socket.
// No CAN or hardware output.
// GID equality is provenance within the local graph, not cryptographic auth.
#include <rclcpp/rclcpp.hpp>
#include <control_msgs/msg/joint_trajectory_controller_state.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <moveit_msgs/msg/servo_status.hpp>
#include <action_msgs/msg/goal_status_array.hpp>
#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <sys/socket.h>
#include <unistd.h>

using Trajectory=trajectory_msgs::msg::JointTrajectory;
using ControllerState=control_msgs::msg::JointTrajectoryControllerState;
using Status=moveit_msgs::msg::ServoStatus;
using Gid=std::array<uint8_t,RMW_GID_STORAGE_SIZE>;
using Steady=std::chrono::steady_clock;
constexpr int64_t MS=1000000;
constexpr int64_t SEC=1000000000;

class Relay final:public rclcpp::Node {
 public:
  explicit Relay(int fd):Node("vision_servo_sample_relay"),fd_(fd) {
    ns_=declare_parameter<std::string>("pipeline_namespace","/vision_manual");
    if(ns_!="/vision_manual" && ns_!="/vision_manual_fixture")
      throw std::runtime_error("fixed pipeline namespace required");
    candidate_=ns_+"/servo_trajectory";
    command_=ns_+"/arm_controller/joint_trajectory";
    state_=ns_+"/arm_controller/controller_state";
    status_=ns_+"/servo_status";
    auto qos=rclcpp::QoS(1).reliable();
    command_pub_=create_publisher<Trajectory>(command_,qos);
    trajectory_=create_subscription<Trajectory>(candidate_,qos,
      [this](Trajectory::ConstSharedPtr m,const rclcpp::MessageInfo& info){window(*m,info);});
    controller_=create_subscription<ControllerState>(state_,qos,
      [this](ControllerState::ConstSharedPtr m,const rclcpp::MessageInfo& info){sample(*m,info);});
    servo_=create_subscription<Status>(status_,qos,
      [this](Status::ConstSharedPtr m,const rclcpp::MessageInfo& info){
        if(!attributed(status_,ns_,"servo_node","moveit_msgs/msg/ServoStatus",info,status_gid_,status_pinned_)) {
          status_code_=-1;return;
        }
        status_code_=m->code;status_time_=Steady::now();
      });
    goal_status_=create_subscription<action_msgs::msg::GoalStatusArray>(
      ns_+"/arm_controller/follow_joint_trajectory/_action/status",rclcpp::QoS(1).reliable().transient_local(),
      [this](action_msgs::msg::GoalStatusArray::ConstSharedPtr m){
        for(const auto& g:m->status_list)
          if(g.status==1||g.status==2||g.status==3)source_changed_=true;
      });
  }
 private:
  bool attributed(const std::string& topic,const std::string& ns,const std::string& name,
                  const std::string& type,const rclcpp::MessageInfo& info,Gid& pin,bool& pinned) {
    const auto list=get_publishers_info_by_topic(topic);
    if(list.size()!=1){if(pinned||list.size()>1)source_changed_=true;return false;}
    const auto& ep=list.front();
    if(ep.node_namespace()!=ns || ep.node_name()!=name || ep.topic_type()!=type){
      // Fast DDS can discover a single endpoint before its participant's
      // node identity. Until the first verified GID, reject these samples
      // without declaring a source replacement. Never accept unknown metadata.
      // After pinning, identity loss (including this placeholder) still latches.
      if(!pinned && ep.topic_type()==type &&
         ep.node_namespace()=="_NODE_NAMESPACE_UNKNOWN_" &&
         ep.node_name()=="_NODE_NAME_UNKNOWN_") {
        RCLCPP_INFO_ONCE(get_logger(), "Waiting for complete DDS source identity");
        return false;
      }
      source_changed_=true;return false;
    }
    Gid actual{};
    const auto& gid=info.get_rmw_message_info().publisher_gid;
    std::copy_n(gid.data,actual.size(),actual.begin());
    const auto& endpoint=ep.endpoint_gid();
    if(!std::equal(actual.begin(),actual.end(),endpoint.begin()))return false;
    if(pinned && pin!=actual){source_changed_=true;return false;}
    if(!pinned){pin=actual;pinned=true;}
    return !source_changed_;
  }
  static bool finite7(const std::vector<double>& a) {
    return a.size()==7 && std::all_of(a.begin(),a.end(),[](double x){return std::isfinite(x);});
  }
  static bool order(const std::vector<std::string>& names,std::array<size_t,7>& indices) {
    if(names.size()!=7)return false;
    for(size_t i=0;i<7;i++){
      std::string name="joint"+std::to_string(i+1);
      auto it=std::find(names.begin(),names.end(),name);
      if(it==names.end() || std::count(names.begin(),names.end(),name)!=1)return false;
      indices[i]=static_cast<size_t>(std::distance(names.begin(),it));
    }
    return true;
  }
  static int64_t stamp(const builtin_interfaces::msg::Time& t) {
    if(t.sec<0||t.nanosec>=SEC)return -1;
    return static_cast<int64_t>(t.sec)*SEC+t.nanosec;
  }
  bool sole_jtc_input() {
    auto rows=get_publishers_info_by_topic(command_);
    if(rows.size()!=1){if(rows.size()>1)source_changed_=true;return false;}
    const auto gid=command_pub_->get_gid();
    if(!std::equal(rows.front().endpoint_gid().begin(),rows.front().endpoint_gid().end(),gid.data)){
      source_changed_=true;return false;
    }
    return !source_changed_;
  }
  void window(const Trajectory& msg,const rclcpp::MessageInfo& info) {
    window_end_=0;
    if(!attributed(candidate_,ns_,"servo_node","trajectory_msgs/msg/JointTrajectory",info,trajectory_gid_,trajectory_pinned_))return;
    std::array<size_t,7> indices{};
    if(!order(msg.joint_names,indices)||msg.points.empty()||msg.points.size()>64||
       (!msg.header.frame_id.empty()&&msg.header.frame_id!="base_link"))return;
    auto now=get_clock()->now().nanoseconds(),start=stamp(msg.header.stamp);
    if(start<=0||start>now+50*MS||now-start>300*MS)return;
    int64_t last=-1;
    for(const auto& p:msg.points) {
      if(p.time_from_start.sec<0||p.time_from_start.nanosec>=SEC)return;
      int64_t d=static_cast<int64_t>(p.time_from_start.sec)*SEC+p.time_from_start.nanosec;
      if(d<=last||d>500*MS||!finite7(p.positions)||!finite7(p.velocities)||
         !p.effort.empty()||(!p.accelerations.empty()&&!finite7(p.accelerations)))return;
      last=d;
    }
    if(start+last<=now||start+last<=last_window_end_)return;
    if(!sole_jtc_input())return;
    // Preserve the complete upstream time window, never replace it by a
    // position or retime it to now. JTC performs the interpolation.
    command_pub_->publish(msg);
    last_window_end_=window_end_=start+last;
    window_time_=Steady::now();
  }
  void sample(const ControllerState& msg,const rclcpp::MessageInfo& info) {
    if(!attributed(state_,ns_,"arm_controller","control_msgs/msg/JointTrajectoryControllerState",info,state_gid_,state_pinned_))return;
    auto now=get_clock()->now().nanoseconds(),s=stamp(msg.header.stamp);
    const auto mono=Steady::now();
    if(s<=0||s>now||now-s>100*MS||s<=last_sample_||
       window_end_<=now||mono-window_time_>std::chrono::milliseconds(150)||
       mono-status_time_>std::chrono::milliseconds(150)||
       !(status_code_==0||status_code_==1||status_code_==3||status_code_==4)||
       !msg.multi_dof_joint_names.empty())return;
    auto current=[this](const std::string& topic,const Gid& pin){
      auto rows=get_publishers_info_by_topic(topic);
      return rows.size()==1 && std::equal(pin.begin(),pin.end(),rows.front().endpoint_gid().begin());
    };
    if(!sole_jtc_input()||!current(candidate_,trajectory_gid_)||!current(status_,status_gid_)){source_changed_=true;return;}
    std::array<size_t,7> indices{};
    if(!order(msg.joint_names,indices)||!finite7(msg.reference.positions)||
       !finite7(msg.reference.velocities))return;
    std::ostringstream json;json.imbue(std::locale::classic());
    json<<std::setprecision(17)<<"{\"stampNs\":"<<s<<",\"windowEndNs\":"<<window_end_
        <<",\"status\":"<<status_code_<<",\"positions\":[";
    for(size_t i=0;i<7;i++){if(i)json<<',';json<<msg.reference.positions[indices[i]];}
    json<<"],\"velocities\":[";
    for(size_t i=0;i<7;i++){if(i)json<<',';json<<msg.reference.velocities[indices[i]];}
    json<<"]}";
    auto data=json.str();
    if(data.size()>2048)return;
    auto n=::send(fd_,data.data(),data.size(),MSG_DONTWAIT|MSG_NOSIGNAL);
    if(n==static_cast<ssize_t>(data.size()))last_sample_=s;
  }
  int fd_;
  std::string ns_,candidate_,command_,state_,status_;
  bool source_changed_=false,trajectory_pinned_=false,state_pinned_=false,status_pinned_=false;
  Gid trajectory_gid_{},state_gid_{},status_gid_{};
  int64_t window_end_=0,last_window_end_=0,last_sample_=0;
  int status_code_=-1;
  Steady::time_point window_time_{},status_time_{};
  rclcpp::Publisher<Trajectory>::SharedPtr command_pub_;
  rclcpp::Subscription<action_msgs::msg::GoalStatusArray>::SharedPtr goal_status_;
  rclcpp::Subscription<Trajectory>::SharedPtr trajectory_;
  rclcpp::Subscription<ControllerState>::SharedPtr controller_;
  rclcpp::Subscription<Status>::SharedPtr servo_;
};

int main(int argc,char** argv) {
  const char* value=std::getenv("VISION_SERVO_RELAY_FD");
  if(!value)return 2;
  char* end=nullptr;long fd=std::strtol(value,&end,10);
  if(!end||*end||fd<3||fd>1024)return 2;
  int type=0;socklen_t len=sizeof(type);
  if(::getsockopt(static_cast<int>(fd),SOL_SOCKET,SO_TYPE,&type,&len)!=0||type!=SOCK_SEQPACKET)return 2;
  try {
    rclcpp::init(argc,argv);
    rclcpp::spin(std::make_shared<Relay>(static_cast<int>(fd)));
    rclcpp::shutdown();
  }catch(const std::exception& e){
    fprintf(stderr,"servo relay: %s\n",e.what());
    return 3;
  }
  return 0;
}
